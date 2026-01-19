"""
Service functions for tax charge business logic.

These functions handle:
- Calculating taxable income
- Enriching tax charges with computed rates
- Getting tax account recommendations
- Filtering tax charges
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from django.db.models import QuerySet

from api.models import Account, TaxCharge
from api.statement import IncomeStatement


@dataclass
class TaxableIncomeData:
    """Data about taxable income for a period."""
    amount: Decimal
    start_date: date
    end_date: date


@dataclass
class TaxChargeWithRate:
    """Tax charge enriched with computed rate information."""
    tax_charge: TaxCharge
    taxable_income: Decimal
    tax_rate: Optional[Decimal]
    current_tax: Optional[Decimal]
    transaction_string: str


@dataclass
class TaxAccountRecommendation:
    """Tax account with recommended tax amount."""
    account: Account
    recommended_tax: Optional[Decimal]


def get_taxable_income(end_date: date) -> TaxableIncomeData:
    """
    Calculate taxable income for the month ending on end_date.

    Uses IncomeStatement to compute taxable income, excluding
    unrealized investment gains and other income.

    Args:
        end_date: The last day of the month to calculate for.

    Returns:
        TaxableIncomeData with amount and date range.
    """
    first_day_of_month = date(end_date.year, end_date.month, 1)
    income_statement = IncomeStatement(end_date, first_day_of_month)
    taxable_income = income_statement.get_taxable_income()

    return TaxableIncomeData(
        amount=taxable_income,
        start_date=first_day_of_month,
        end_date=end_date,
    )


def enrich_tax_charges_with_rates(
    tax_charges: QuerySet[TaxCharge],
    current_taxable_income: Optional[Decimal] = None,
) -> List[TaxChargeWithRate]:
    """
    Enrich tax charges with computed tax rates and current tax amounts.

    Caches IncomeStatement by date to avoid redundant calculations
    when multiple tax charges share the same date.

    Args:
        tax_charges: QuerySet of TaxCharge objects.
        current_taxable_income: Optional current period's taxable income
            for calculating current_tax projections.

    Returns:
        List of TaxChargeWithRate objects with computed fields.
    """
    tax_charges = tax_charges.select_related(
        "transaction", "transaction__account"
    ).order_by("date", "account")

    # Cache taxable income by date to limit IncomeStatement creations
    taxable_income_cache: Dict[date, Decimal] = {}
    enriched_charges: List[TaxChargeWithRate] = []

    for tax_charge in tax_charges:
        # Get or compute taxable income for this date
        if tax_charge.date not in taxable_income_cache:
            income_data = get_taxable_income(tax_charge.date)
            taxable_income_cache[tax_charge.date] = income_data.amount

        taxable_income = taxable_income_cache[tax_charge.date]

        # Calculate tax rate
        if taxable_income == 0:
            tax_rate = None
        else:
            tax_rate = tax_charge.amount / taxable_income

        # Calculate current tax projection if we have both rate and current income
        if current_taxable_income and tax_rate:
            current_tax = tax_rate * current_taxable_income
        else:
            current_tax = None

        enriched_charges.append(
            TaxChargeWithRate(
                tax_charge=tax_charge,
                taxable_income=taxable_income,
                tax_rate=tax_rate,
                current_tax=current_tax,
                transaction_string=str(tax_charge.transaction),
            )
        )

    return enriched_charges


def get_tax_account_recommendations(
    taxable_income: Decimal,
) -> List[TaxAccountRecommendation]:
    """
    Get all tax accounts with their recommended tax amounts.

    Calculates recommended tax based on either:
    - account.tax_rate * taxable_income (for percentage-based taxes)
    - account.tax_amount (for fixed amount taxes like property tax)

    Args:
        taxable_income: The taxable income amount.

    Returns:
        List of TaxAccountRecommendation objects.
    """
    tax_accounts = Account.objects.filter(
        special_type__in=[
            Account.SpecialType.FEDERAL_TAXES,
            Account.SpecialType.STATE_TAXES,
            Account.SpecialType.PROPERTY_TAXES,
        ]
    )

    recommendations: List[TaxAccountRecommendation] = []

    for account in tax_accounts:
        if account.tax_rate:
            recommended_tax = account.tax_rate * taxable_income
        elif account.tax_amount:
            recommended_tax = account.tax_amount
        else:
            recommended_tax = None

        recommendations.append(
            TaxAccountRecommendation(
                account=account,
                recommended_tax=recommended_tax,
            )
        )

    return recommendations


def get_filtered_tax_charges(
    date_from: date,
    date_to: date,
    tax_type: Optional[Account] = None,
) -> QuerySet[TaxCharge]:
    """
    Filter tax charges by date range and optionally by tax account.

    Args:
        date_from: Start of date range (inclusive).
        date_to: End of date range (inclusive).
        tax_type: Optional account to filter by.

    Returns:
        QuerySet of filtered TaxCharge objects.
    """
    queryset = TaxCharge.objects.filter(
        date__gte=date_from,
        date__lte=date_to,
    )

    if tax_type:
        queryset = queryset.filter(transaction__account=tax_type)

    return queryset.order_by("date")
