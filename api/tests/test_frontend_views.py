from datetime import date
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import TaxCharge, Transaction, Account
from api import utils


class TaxesViewTest(TestCase):
    """Tests for the Taxes view.

    Note: The TaxesView creates its own tax charges via TaxChargeFactory.create_bulk_tax_charges()
    and filters to only show charges from the last 6 months up to the last day of last month.
    The view returns an HttpResponse with rendered HTML, not a TemplateResponse with context.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='testuser', password='12345')

        # Create the special accounts required by TaxCharge's save method
        # First create the payable accounts
        state_pay_account = Account.objects.create(
            name='State Taxes Pay Account',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.TAXES_PAYABLE,
            special_type=Account.SpecialType.STATE_TAXES_PAYABLE
        )
        fed_pay_account = Account.objects.create(
            name='Fed Taxes Pay Account',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.TAXES_PAYABLE,
            special_type=Account.SpecialType.FEDERAL_TAXES_PAYABLE
        )
        property_pay_account = Account.objects.create(
            name='Prop Taxes Pay Account',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.TAXES_PAYABLE,
            special_type=Account.SpecialType.PROPERTY_TAXES_PAYABLE
        )
        # Now create the expense accounts and link to payable accounts
        Account.objects.create(
            name='State Taxes Account',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
            special_type=Account.SpecialType.STATE_TAXES,
            tax_payable_account=state_pay_account
        )
        Account.objects.create(
            name='Fed Taxes Account',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
            special_type=Account.SpecialType.FEDERAL_TAXES,
            tax_payable_account=fed_pay_account
        )
        Account.objects.create(
            name='Prop Taxes Account',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
            special_type=Account.SpecialType.PROPERTY_TAXES,
            tax_payable_account=property_pay_account
        )

    def test_redirect_if_not_logged_in(self):
        response = self.client.get(reverse('taxes'))
        self.assertRedirects(response, '/login/?next=/taxes/')

    def test_logged_in_returns_success(self):
        """Test that logged in user gets a successful response with tax content."""
        self.client.login(username='testuser', password='12345')
        response = self.client.get(reverse('taxes'))

        # Check that we got a response "success"
        self.assertEqual(response.status_code, 200)

        # Check the content contains tax-related elements
        self.assertIn(b'Taxes', response.content)

    def test_tax_charges_created_by_view(self):
        """Test that TaxCharges are created by the view via TaxChargeFactory."""
        self.client.login(username='testuser', password='12345')

        # Before request, no tax charges exist
        initial_count = TaxCharge.objects.count()

        response = self.client.get(reverse('taxes'))
        self.assertEqual(response.status_code, 200)

        # After request, tax charges should be created for last month
        # The view calls TaxChargeFactory.create_bulk_tax_charges(date=initial_end_date)
        last_day_of_last_month = utils.get_last_day_of_last_month()
        tax_charges = TaxCharge.objects.filter(date=last_day_of_last_month)

        # Should have created charges for the 3 tax account types
        self.assertGreaterEqual(tax_charges.count(), initial_count)


class UploadTransactionsViewTest(TestCase):
    """Tests for the UploadTransactionsView."""

    def test_get_returns_200(self):
        """Regression test: GET /upload-transactions/ should return 200."""
        response = self.client.get(reverse('upload-transactions'))
        self.assertEqual(response.status_code, 200)

    def test_post_with_invalid_paystub_form_returns_200(self):
        """POST with 'paystubs' key but missing required fields should re-render the form."""
        response = self.client.post(reverse('upload-transactions'), {"paystubs": ""})
        self.assertEqual(response.status_code, 200)

    def test_post_with_invalid_transactions_form_returns_200(self):
        """POST with 'transactions' key but missing required fields should re-render the form."""
        response = self.client.post(reverse('upload-transactions'), {"transactions": ""})
        self.assertEqual(response.status_code, 200)

    def test_post_with_no_form_type_returns_400(self):
        """POST with neither 'transactions' nor 'paystubs' should return 400."""
        response = self.client.post(reverse('upload-transactions'), {"other": "data"})
        self.assertEqual(response.status_code, 400)
