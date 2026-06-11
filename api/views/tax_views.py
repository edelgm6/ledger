"""
Tax charge views.

These views handle HTTP orchestration for tax charge pages,
delegating to tax_services for business logic and tax_helpers for rendering.
"""

from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from api import utils
from api.factories import TaxChargeFactory
from api.forms import TaxChargeFilterForm, TaxChargeForm
from api.models import TaxCharge
from api.services import tax_services
from api.views import tax_helpers
from api.views.page_utils import render_full_page


def _parse_date(value):
    """Convert a string date (YYYY-MM-DD) to a date object, or return as-is if already a date."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _build_table_and_form(tax_charges, end_date: date):
    """
    Build the tax table + form HTML for a set of charges and the month-end date.

    Returns a (table_html, form_html) tuple. Shared by every taxes view so the
    enrich → taxable-income → recommendations → render pipeline lives in one
    place.
    """
    enriched = tax_services.enrich_tax_charges_with_rates(tax_charges)
    taxable_income = tax_services.get_taxable_income(end_date)
    recommendations = tax_services.get_tax_account_recommendations(
        taxable_income.amount
    )

    table_html = tax_helpers.render_tax_table(enriched)
    form_html = tax_helpers.render_tax_form(
        None, taxable_income.amount, recommendations, end_date
    )
    return table_html, form_html


def _render_updated_content(data) -> str:
    """
    Re-render the taxes table + form for an HTMX update.

    Honors the submitted filter form (date range / tax type) so the refreshed
    content matches the user's current filter, falling back to the default
    six-month window when the filter form is absent or invalid.
    """
    filter_form = TaxChargeFilterForm(data)
    if filter_form.is_valid():
        date_from = _parse_date(filter_form.cleaned_data["date_from"])
        end_date = _parse_date(filter_form.cleaned_data["date_to"])
        tax_charges = tax_services.get_filtered_tax_charges(
            date_from=date_from,
            date_to=end_date,
            tax_type=filter_form.cleaned_data.get("tax_type"),
        )
    else:
        # Fallback to default date range
        end_date = utils.get_last_day_of_last_month()
        six_months_ago = utils.get_last_days_of_month_tuples()[5][0]
        tax_charges = tax_services.get_filtered_tax_charges(
            date_from=six_months_ago, date_to=end_date
        )

    table_html, form_html = _build_table_and_form(tax_charges, end_date)
    return tax_helpers.render_taxes_content(table_html, form_html)


class TaxChargeTableView(LoginRequiredMixin, View):
    """Handle tax charge table filtering."""

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, *args, **kwargs):
        return HttpResponse(_render_updated_content(request.GET))


class TaxChargeFormView(LoginRequiredMixin, View):
    """Handle tax charge form rendering for edit/create."""

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, pk=None, *args, **kwargs):
        tax_charge = get_object_or_404(TaxCharge, pk=pk) if pk else None
        end_date = (
            tax_charge.date if tax_charge else utils.get_last_day_of_last_month()
        )

        taxable_income = tax_services.get_taxable_income(end_date)
        recommendations = tax_services.get_tax_account_recommendations(
            taxable_income.amount
        )
        html = tax_helpers.render_tax_form(
            tax_charge, taxable_income.amount, recommendations, end_date
        )
        return HttpResponse(html)


class TaxesView(LoginRequiredMixin, View):
    """Handle full taxes page and tax charge creation/updates."""

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, *args, **kwargs):
        initial_end_date = utils.get_last_day_of_last_month()
        TaxChargeFactory.create_bulk_tax_charges(date=initial_end_date)

        six_months_ago = utils.get_last_days_of_month_tuples()[5][0]
        tax_charges = tax_services.get_filtered_tax_charges(
            date_from=six_months_ago, date_to=initial_end_date
        )

        table_html, form_html = _build_table_and_form(tax_charges, initial_end_date)
        filter_html = tax_helpers.render_tax_filter_form()

        html = tax_helpers.render_taxes_page(table_html, form_html, filter_html)
        return render_full_page(request, html)

    def post(self, request, pk=None, *args, **kwargs):
        tax_charge = get_object_or_404(TaxCharge, pk=pk) if pk else None
        form = TaxChargeForm(data=request.POST, instance=tax_charge)

        if form.is_valid():
            form.save()

        return HttpResponse(_render_updated_content(request.POST))


class ApplyTaxRecommendationView(LoginRequiredMixin, View):
    """Apply a calculated tax recommendation directly to an account's charge."""

    login_url = "/login/"
    redirect_field_name = "next"

    def post(self, request, account_pk, end_date, *args, **kwargs):
        result = tax_services.apply_tax_recommendation(
            account_pk, _parse_date(end_date)
        )
        if not result.success:
            return HttpResponse(result.error, status=400)

        return HttpResponse(_render_updated_content(request.POST))
