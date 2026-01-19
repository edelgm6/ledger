"""
Tests for tax_services.py functions.

Tests cover:
- get_taxable_income: Calculating taxable income for a month
- enrich_tax_charges_with_rates: Computing tax rates and projections
- get_tax_account_recommendations: Tax account recommendations
- get_filtered_tax_charges: Filtering tax charges by date/type
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase

from api.models import Account, TaxCharge, Transaction
from api.services.tax_services import (
    TaxableIncomeData,
    TaxChargeWithRate,
    TaxAccountRecommendation,
    get_taxable_income,
    enrich_tax_charges_with_rates,
    get_tax_account_recommendations,
    get_filtered_tax_charges,
)
from api.tests.testing_factories import (
    AccountFactory,
    TransactionFactory,
)


class GetTaxableIncomeTest(TestCase):
    """Tests for get_taxable_income() function."""

    @patch("api.services.tax_services.IncomeStatement")
    def test_returns_taxable_income_data(self, mock_income_statement_class):
        """Test returns TaxableIncomeData with correct structure."""
        mock_income_statement = MagicMock()
        mock_income_statement.get_taxable_income.return_value = Decimal("5000.00")
        mock_income_statement_class.return_value = mock_income_statement

        end_date = date(2024, 1, 31)
        result = get_taxable_income(end_date)

        self.assertIsInstance(result, TaxableIncomeData)
        self.assertEqual(result.amount, Decimal("5000.00"))
        self.assertEqual(result.start_date, date(2024, 1, 1))
        self.assertEqual(result.end_date, date(2024, 1, 31))

    @patch("api.services.tax_services.IncomeStatement")
    def test_creates_income_statement_with_correct_dates(self, mock_income_statement_class):
        """Test IncomeStatement is created with month start and end dates."""
        mock_income_statement = MagicMock()
        mock_income_statement.get_taxable_income.return_value = Decimal("0")
        mock_income_statement_class.return_value = mock_income_statement

        end_date = date(2024, 3, 31)
        get_taxable_income(end_date)

        mock_income_statement_class.assert_called_once_with(
            date(2024, 3, 31),
            date(2024, 3, 1),
        )

    @patch("api.services.tax_services.IncomeStatement")
    def test_handles_zero_income(self, mock_income_statement_class):
        """Test correctly handles months with no taxable income."""
        mock_income_statement = MagicMock()
        mock_income_statement.get_taxable_income.return_value = Decimal("0")
        mock_income_statement_class.return_value = mock_income_statement

        result = get_taxable_income(date(2024, 1, 31))

        self.assertEqual(result.amount, Decimal("0"))


class EnrichTaxChargesWithRatesTest(TestCase):
    """Tests for enrich_tax_charges_with_rates() function."""

    def setUp(self):
        """Create test accounts and tax charges."""
        # Create a tax payable account for the relationship
        self.tax_payable = AccountFactory(
            type=Account.Type.LIABILITY,
        )
        # Create a tax account
        self.tax_account = AccountFactory(
            type=Account.Type.EXPENSE,
            special_type=Account.SpecialType.FEDERAL_TAXES,
            tax_payable_account=self.tax_payable,
        )

    @patch("api.services.tax_services.get_taxable_income")
    def test_calculates_tax_rate_correctly(self, mock_get_taxable_income):
        """Test tax rate is calculated as amount / taxable_income."""
        mock_get_taxable_income.return_value = TaxableIncomeData(
            amount=Decimal("10000.00"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        # Create a tax charge
        tax_charge = TaxCharge.objects.create(
            account=self.tax_account,
            date=date(2024, 1, 31),
            amount=Decimal("2500.00"),
        )

        tax_charges = TaxCharge.objects.filter(pk=tax_charge.pk)
        result = enrich_tax_charges_with_rates(tax_charges)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].tax_rate, Decimal("0.25"))  # 2500 / 10000

    @patch("api.services.tax_services.get_taxable_income")
    def test_handles_zero_taxable_income(self, mock_get_taxable_income):
        """Test tax rate is None when taxable income is zero."""
        mock_get_taxable_income.return_value = TaxableIncomeData(
            amount=Decimal("0"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        tax_charge = TaxCharge.objects.create(
            account=self.tax_account,
            date=date(2024, 1, 31),
            amount=Decimal("100.00"),
        )

        tax_charges = TaxCharge.objects.filter(pk=tax_charge.pk)
        result = enrich_tax_charges_with_rates(tax_charges)

        self.assertIsNone(result[0].tax_rate)

    @patch("api.services.tax_services.get_taxable_income")
    def test_caches_income_by_date(self, mock_get_taxable_income):
        """Test IncomeStatement is only created once per unique date."""
        mock_get_taxable_income.return_value = TaxableIncomeData(
            amount=Decimal("10000.00"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        # Create two tax charges with same date
        TaxCharge.objects.create(
            account=self.tax_account,
            date=date(2024, 1, 31),
            amount=Decimal("1000.00"),
        )

        # Create another tax account for the second charge (needs its own tax_payable)
        second_tax_payable = AccountFactory(
            type=Account.Type.LIABILITY,
        )
        second_tax_account = AccountFactory(
            type=Account.Type.EXPENSE,
            special_type=Account.SpecialType.STATE_TAXES,
            tax_payable_account=second_tax_payable,
        )

        TaxCharge.objects.create(
            account=second_tax_account,
            date=date(2024, 1, 31),
            amount=Decimal("500.00"),
        )

        tax_charges = TaxCharge.objects.filter(date=date(2024, 1, 31))
        enrich_tax_charges_with_rates(tax_charges)

        # Should only call get_taxable_income once since both have same date
        self.assertEqual(mock_get_taxable_income.call_count, 1)

    @patch("api.services.tax_services.get_taxable_income")
    def test_calculates_current_tax_when_provided(self, mock_get_taxable_income):
        """Test current_tax is calculated when current_taxable_income provided."""
        mock_get_taxable_income.return_value = TaxableIncomeData(
            amount=Decimal("10000.00"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        tax_charge = TaxCharge.objects.create(
            account=self.tax_account,
            date=date(2024, 1, 31),
            amount=Decimal("2500.00"),  # 25% rate
        )

        tax_charges = TaxCharge.objects.filter(pk=tax_charge.pk)
        result = enrich_tax_charges_with_rates(
            tax_charges,
            current_taxable_income=Decimal("8000.00"),
        )

        # current_tax = 0.25 * 8000 = 2000
        self.assertEqual(result[0].current_tax, Decimal("2000.00"))

    @patch("api.services.tax_services.get_taxable_income")
    def test_returns_enriched_data_structure(self, mock_get_taxable_income):
        """Test returns TaxChargeWithRate with all fields populated."""
        mock_get_taxable_income.return_value = TaxableIncomeData(
            amount=Decimal("10000.00"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        tax_charge = TaxCharge.objects.create(
            account=self.tax_account,
            date=date(2024, 1, 31),
            amount=Decimal("2000.00"),
        )

        tax_charges = TaxCharge.objects.filter(pk=tax_charge.pk)
        result = enrich_tax_charges_with_rates(tax_charges)

        self.assertIsInstance(result[0], TaxChargeWithRate)
        self.assertEqual(result[0].tax_charge, tax_charge)
        self.assertEqual(result[0].taxable_income, Decimal("10000.00"))
        self.assertEqual(result[0].tax_rate, Decimal("0.2"))
        self.assertIsNone(result[0].current_tax)
        self.assertIsInstance(result[0].transaction_string, str)


class GetTaxAccountRecommendationsTest(TestCase):
    """Tests for get_tax_account_recommendations() function."""

    def test_returns_recommendations_for_tax_accounts(self):
        """Test returns recommendations for all tax accounts."""
        federal = AccountFactory(
            type=Account.Type.EXPENSE,
            special_type=Account.SpecialType.FEDERAL_TAXES,
            tax_rate=Decimal("0.25"),
        )
        state = AccountFactory(
            type=Account.Type.EXPENSE,
            special_type=Account.SpecialType.STATE_TAXES,
            tax_rate=Decimal("0.05"),
        )

        result = get_tax_account_recommendations(Decimal("10000.00"))

        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], TaxAccountRecommendation)

    def test_uses_tax_rate_when_set(self):
        """Test recommended tax uses tax_rate * taxable_income."""
        federal = AccountFactory(
            type=Account.Type.EXPENSE,
            special_type=Account.SpecialType.FEDERAL_TAXES,
            tax_rate=Decimal("0.25"),
            tax_amount=None,
        )

        result = get_tax_account_recommendations(Decimal("10000.00"))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].recommended_tax, Decimal("2500.00"))

    def test_uses_tax_amount_when_set(self):
        """Test recommended tax uses tax_amount for fixed taxes."""
        property_tax = AccountFactory(
            type=Account.Type.EXPENSE,
            special_type=Account.SpecialType.PROPERTY_TAXES,
            tax_rate=None,
            tax_amount=Decimal("500.00"),
        )

        result = get_tax_account_recommendations(Decimal("10000.00"))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].recommended_tax, Decimal("500.00"))

    def test_returns_none_when_neither_set(self):
        """Test recommended tax is None when account has no rate or amount."""
        federal = AccountFactory(
            type=Account.Type.EXPENSE,
            special_type=Account.SpecialType.FEDERAL_TAXES,
            tax_rate=None,
            tax_amount=None,
        )

        result = get_tax_account_recommendations(Decimal("10000.00"))

        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0].recommended_tax)

    def test_excludes_non_tax_accounts(self):
        """Test only tax accounts are included."""
        # Create a non-tax account
        AccountFactory(
            type=Account.Type.EXPENSE,
            special_type=None,
        )
        # Create a tax account
        federal = AccountFactory(
            type=Account.Type.EXPENSE,
            special_type=Account.SpecialType.FEDERAL_TAXES,
            tax_rate=Decimal("0.25"),
        )

        result = get_tax_account_recommendations(Decimal("10000.00"))

        # Should only return the federal tax account
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].account.special_type, Account.SpecialType.FEDERAL_TAXES)


class GetFilteredTaxChargesTest(TestCase):
    """Tests for get_filtered_tax_charges() function."""

    def setUp(self):
        """Create test accounts and tax charges."""
        # Each account needs its own tax payable account (unique constraint)
        self.federal_tax_payable = AccountFactory(type=Account.Type.LIABILITY)
        self.state_tax_payable = AccountFactory(type=Account.Type.LIABILITY)

        self.federal_account = AccountFactory(
            type=Account.Type.EXPENSE,
            special_type=Account.SpecialType.FEDERAL_TAXES,
            tax_payable_account=self.federal_tax_payable,
        )
        self.state_account = AccountFactory(
            type=Account.Type.EXPENSE,
            special_type=Account.SpecialType.STATE_TAXES,
            tax_payable_account=self.state_tax_payable,
        )

    def test_filters_by_date_range(self):
        """Test filters tax charges within date range."""
        # Create charges at different dates
        TaxCharge.objects.create(
            account=self.federal_account,
            date=date(2024, 1, 31),
            amount=Decimal("1000.00"),
        )
        TaxCharge.objects.create(
            account=self.federal_account,
            date=date(2024, 2, 29),
            amount=Decimal("1100.00"),
        )
        # Outside range
        TaxCharge.objects.create(
            account=self.state_account,
            date=date(2024, 3, 31),
            amount=Decimal("500.00"),
        )

        result = get_filtered_tax_charges(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 2, 29),
        )

        self.assertEqual(result.count(), 2)

    def test_filters_by_tax_type(self):
        """Test filters tax charges by account type."""
        TaxCharge.objects.create(
            account=self.federal_account,
            date=date(2024, 1, 31),
            amount=Decimal("1000.00"),
        )
        TaxCharge.objects.create(
            account=self.state_account,
            date=date(2024, 1, 31),
            amount=Decimal("500.00"),
        )

        result = get_filtered_tax_charges(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 31),
            tax_type=self.federal_account,
        )

        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().account, self.federal_account)

    def test_returns_queryset(self):
        """Test returns a QuerySet that can be further filtered."""
        TaxCharge.objects.create(
            account=self.federal_account,
            date=date(2024, 1, 31),
            amount=Decimal("1000.00"),
        )

        result = get_filtered_tax_charges(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 31),
        )

        # Should be a QuerySet, not a list
        from django.db.models import QuerySet
        self.assertIsInstance(result, QuerySet)

    def test_orders_by_date(self):
        """Test results are ordered by date."""
        TaxCharge.objects.create(
            account=self.federal_account,
            date=date(2024, 2, 29),
            amount=Decimal("1100.00"),
        )
        TaxCharge.objects.create(
            account=self.state_account,
            date=date(2024, 1, 31),
            amount=Decimal("1000.00"),
        )

        result = list(get_filtered_tax_charges(
            date_from=date(2024, 1, 1),
            date_to=date(2024, 2, 29),
        ))

        self.assertEqual(result[0].date, date(2024, 1, 31))
        self.assertEqual(result[1].date, date(2024, 2, 29))
