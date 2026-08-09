"""
Views for the CSV Profiles Settings section.

Loaded as an HTML fragment into the Settings shell: config CRUD over CSVProfile
(mirrors AutoTagSettingsView / EntitySettingsView).

Views parse requests, call services for business logic, and call helpers for
rendering. No database writes and no HTML building here.
"""

from typing import Optional

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from api.forms import CSVProfileForm
from api.models import CSVProfile
from api.services import csv_profile_services
from api.views import csv_settings_helpers


class CSVProfileSettingsView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def _render_content(
        self,
        csv_profile: Optional[CSVProfile] = None,
        change: Optional[str] = None,
        error: Optional[str] = None,
        form: Optional[CSVProfileForm] = None,
        selected_id: Optional[int] = None,
    ) -> str:
        """Builds the swappable CSV Profiles fragment (header + table + form)."""
        csv_profile_form_html = csv_settings_helpers.render_csv_profile_form(
            csv_profile=csv_profile,
            change=change,
            error=error,
            form=form,
        )
        csv_profiles = csv_profile_services.get_csv_profiles()
        return csv_settings_helpers.render_csv_profiles_content(
            csv_profiles=csv_profiles,
            csv_profile_form_html=csv_profile_form_html,
            selected_id=selected_id,
        )

    def get(self, request):
        return HttpResponse(self._render_content())

    def post(self, request, csv_profile_id=None):
        action = request.POST.get("action")

        if action == "clear":
            return HttpResponse(self._render_content())

        if action == "delete":
            result = csv_profile_services.delete_csv_profile(csv_profile_id)
            if result.success:
                return HttpResponse(self._render_content(change="delete"))
            return HttpResponse(
                self._render_content(
                    csv_profile=result.csv_profile,
                    error=result.error,
                    selected_id=(
                        result.csv_profile.id if result.csv_profile else None
                    ),
                )
            )

        if csv_profile_id:
            csv_profile = get_object_or_404(CSVProfile, pk=csv_profile_id)
            form = CSVProfileForm(request.POST, instance=csv_profile)
            change = "update"
        else:
            csv_profile = None
            form = CSVProfileForm(request.POST)
            change = "create"

        if not form.is_valid():
            return HttpResponse(
                self._render_content(
                    csv_profile=csv_profile,
                    form=form,
                    selected_id=csv_profile.id if csv_profile else None,
                )
            )

        result = csv_profile_services.save_csv_profile(
            form.cleaned_data, instance=csv_profile
        )
        if not result.success:
            return HttpResponse(
                self._render_content(
                    csv_profile=csv_profile,
                    form=form,
                    error=result.error,
                    selected_id=csv_profile.id if csv_profile else None,
                )
            )

        return HttpResponse(
            self._render_content(
                csv_profile=result.csv_profile,
                change=change,
                selected_id=result.csv_profile.id,
            )
        )


class CSVProfileFormView(LoginRequiredMixin, View):
    """Loads a CSV profile (or a blank create form) into the edit form.

    Used on table row clicks (existing profile) and the New CSV Profile button
    (no csv_profile_id -> blank form).
    """

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, csv_profile_id=None):
        csv_profile = (
            get_object_or_404(CSVProfile, pk=csv_profile_id)
            if csv_profile_id
            else None
        )
        form_html = csv_settings_helpers.render_csv_profile_form(
            csv_profile=csv_profile
        )
        return HttpResponse(form_html)
