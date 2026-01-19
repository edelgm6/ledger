"""
Helper functions for rendering tax charge HTML.

These pure functions handle all HTML rendering for tax views,
replacing the rendering logic from TaxChargeMixIn.
"""

from decimal import Decimal
from typing import List, Optional

from django.template.loader import render_to_string

from api.forms import TaxChargeFilterForm, TaxChargeForm
from api.models import TaxCharge
from api.services.tax_services import TaxAccountRecommendation, TaxChargeWithRate


def render_tax_filter_form() -> str:
    """
    Render the tax charge filter form HTML.

    Returns:
        HTML string for the filter form.
    """
    filter_form = TaxChargeFilterForm()
    return render_to_string(
        "api/filter_forms/tax-charge-filter-form.html",
        {"filter_form": filter_form},
    )


def render_tax_form(
    tax_charge: Optional[TaxCharge],
    taxable_income: Decimal,
    tax_accounts: List[TaxAccountRecommendation],
) -> str:
    """
    Render the tax charge entry form HTML.

    Args:
        tax_charge: Optional existing tax charge to edit.
        taxable_income: Current taxable income amount.
        tax_accounts: List of tax accounts with recommended amounts.

    Returns:
        HTML string for the tax form.
    """
    if tax_charge:
        form = TaxChargeForm(instance=tax_charge)
    else:
        form = TaxChargeForm()

    # Convert TaxAccountRecommendation to format expected by template
    # Template expects account objects with recommended_tax attribute
    accounts_with_recommendations = []
    for rec in tax_accounts:
        # Attach recommended_tax to account object for template
        rec.account.recommended_tax = rec.recommended_tax
        accounts_with_recommendations.append(rec.account)

    context = {
        "form": form,
        "taxable_income": taxable_income,
        "tax_accounts": accounts_with_recommendations,
        "tax_charge": tax_charge,
    }

    return render_to_string(
        "api/entry_forms/edit-tax-charge-form.html",
        context,
    )


def render_tax_table(
    tax_charges_with_rates: List[TaxChargeWithRate],
) -> str:
    """
    Render the tax charge table HTML.

    Args:
        tax_charges_with_rates: List of enriched tax charge objects.

    Returns:
        HTML string for the tax table.
    """
    # Convert TaxChargeWithRate to format expected by template
    # Template expects tax_charge objects with attached computed fields
    enriched_charges = []
    for item in tax_charges_with_rates:
        tax_charge = item.tax_charge
        tax_charge.taxable_income = item.taxable_income
        tax_charge.tax_rate = item.tax_rate
        tax_charge.current_tax = item.current_tax
        tax_charge.transaction_string = item.transaction_string
        enriched_charges.append(tax_charge)

    return render_to_string(
        "api/tables/tax-table.html",
        {"tax_charges": enriched_charges},
    )


def render_taxes_content(
    table_html: str,
    form_html: str,
) -> str:
    """
    Render the taxes content section (table + form).

    Used for HTMX partial page updates.

    Args:
        table_html: Pre-rendered tax table HTML.
        form_html: Pre-rendered tax form HTML.

    Returns:
        HTML string for the taxes content.
    """
    return render_to_string(
        "api/content/taxes-content.html",
        {
            "tax_charge_table": table_html,
            "form": form_html,
        },
    )


def render_taxes_page(
    table_html: str,
    form_html: str,
    filter_form_html: str,
) -> str:
    """
    Render the full taxes page HTML.

    Args:
        table_html: Pre-rendered tax table HTML.
        form_html: Pre-rendered tax form HTML.
        filter_form_html: Pre-rendered filter form HTML.

    Returns:
        HTML string for the full taxes page.
    """
    return render_to_string(
        "api/views/taxes.html",
        {
            "tax_charge_table": table_html,
            "form": form_html,
            "filter_form": filter_form_html,
        },
    )
