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


def _parse_date(value):
    """Convert a string date (YYYY-MM-DD) to a date object, or return as-is if already a date."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


class TaxChargeTableView(LoginRequiredMixin, View):
    """Handle tax charge table filtering."""

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, *args, **kwargs):
        form = TaxChargeFilterForm(request.GET)
        if form.is_valid():
            date_from = _parse_date(form.cleaned_data["date_from"])
            date_to = _parse_date(form.cleaned_data["date_to"])

            tax_charges = tax_services.get_filtered_tax_charges(
                date_from=date_from,
                date_to=date_to,
                tax_type=form.cleaned_data.get("tax_type"),
            )
            enriched = tax_services.enrich_tax_charges_with_rates(tax_charges)
            table_html = tax_helpers.render_tax_table(enriched)

            taxable_income = tax_services.get_taxable_income(date_to)
            recommendations = tax_services.get_tax_account_recommendations(
                taxable_income.amount
            )
            form_html = tax_helpers.render_tax_form(
                None, taxable_income.amount, recommendations
            )

            html = tax_helpers.render_taxes_content(table_html, form_html)
            return HttpResponse(html)


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
            tax_charge, taxable_income.amount, recommendations
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
        enriched = tax_services.enrich_tax_charges_with_rates(tax_charges)

        taxable_income = tax_services.get_taxable_income(initial_end_date)
        recommendations = tax_services.get_tax_account_recommendations(
            taxable_income.amount
        )

        table_html = tax_helpers.render_tax_table(enriched)
        form_html = tax_helpers.render_tax_form(
            None, taxable_income.amount, recommendations
        )
        filter_html = tax_helpers.render_tax_filter_form()

        html = tax_helpers.render_taxes_page(table_html, form_html, filter_html)
        return HttpResponse(html)

    def post(self, request, pk=None, *args, **kwargs):
        tax_charge = get_object_or_404(TaxCharge, pk=pk) if pk else None
        form = TaxChargeForm(data=request.POST, instance=tax_charge)

        if form.is_valid():
            form.save()

        # Re-render with updated data
        filter_form = TaxChargeFilterForm(request.POST)
        if filter_form.is_valid():
            date_from = _parse_date(filter_form.cleaned_data["date_from"])
            date_to = _parse_date(filter_form.cleaned_data["date_to"])
            tax_charges = tax_services.get_filtered_tax_charges(
                date_from=date_from,
                date_to=date_to,
                tax_type=filter_form.cleaned_data.get("tax_type"),
            )
            end_date = date_to
        else:
            # Fallback to default date range
            initial_end_date = utils.get_last_day_of_last_month()
            six_months_ago = utils.get_last_days_of_month_tuples()[5][0]
            tax_charges = tax_services.get_filtered_tax_charges(
                date_from=six_months_ago, date_to=initial_end_date
            )
            end_date = initial_end_date

        enriched = tax_services.enrich_tax_charges_with_rates(tax_charges)
        taxable_income = tax_services.get_taxable_income(end_date)
        recommendations = tax_services.get_tax_account_recommendations(
            taxable_income.amount
        )

        table_html = tax_helpers.render_tax_table(enriched)
        form_html = tax_helpers.render_tax_form(
            None, taxable_income.amount, recommendations
        )

        html = tax_helpers.render_taxes_content(table_html, form_html)
        return HttpResponse(html)
