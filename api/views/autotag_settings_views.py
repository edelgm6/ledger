"""
Views for the Autotags Settings section.

Loaded as an HTML fragment into the Settings shell: config CRUD over AutoTag
(mirrors EntitySettingsView / PrefillSettingsView).

Views parse requests, call services for business logic, and call helpers for
rendering. No database writes and no HTML building here.
"""

from typing import Optional

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from api.forms import AutoTagForm
from api.models import AutoTag
from api.services import autotag_services
from api.views import autotag_settings_helpers


class AutoTagSettingsView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def _render_content(
        self,
        autotag: Optional[AutoTag] = None,
        change: Optional[str] = None,
        error: Optional[str] = None,
        form: Optional[AutoTagForm] = None,
        selected_id: Optional[int] = None,
    ) -> str:
        """Builds the swappable Autotags fragment (header + table + form)."""
        accounts, prefills, entities = autotag_services.get_autotag_form_options()
        autotag_form_html = autotag_settings_helpers.render_autotag_form(
            accounts=accounts,
            prefills=prefills,
            entities=entities,
            autotag=autotag,
            change=change,
            error=error,
            form=form,
        )
        autotags = autotag_services.get_autotags()
        return autotag_settings_helpers.render_autotags_content(
            autotags=autotags,
            autotag_form_html=autotag_form_html,
            selected_id=selected_id,
        )

    def get(self, request):
        return HttpResponse(self._render_content())

    def post(self, request, autotag_id=None):
        action = request.POST.get("action")

        if action == "clear":
            return HttpResponse(self._render_content())

        if action == "delete":
            result = autotag_services.delete_autotag(autotag_id)
            if result.success:
                return HttpResponse(self._render_content(change="delete"))
            return HttpResponse(
                self._render_content(
                    autotag=result.autotag,
                    error=result.error,
                    selected_id=result.autotag.id if result.autotag else None,
                )
            )

        if autotag_id:
            autotag = get_object_or_404(AutoTag, pk=autotag_id)
            form = AutoTagForm(request.POST, instance=autotag)
            change = "update"
        else:
            autotag = None
            form = AutoTagForm(request.POST)
            change = "create"

        if not form.is_valid():
            return HttpResponse(
                self._render_content(
                    autotag=autotag,
                    form=form,
                    selected_id=autotag.id if autotag else None,
                )
            )

        result = autotag_services.save_autotag(
            form.cleaned_data, instance=autotag
        )
        if not result.success:
            return HttpResponse(
                self._render_content(
                    autotag=autotag,
                    form=form,
                    error=result.error,
                    selected_id=autotag.id if autotag else None,
                )
            )

        return HttpResponse(
            self._render_content(
                autotag=result.autotag,
                change=change,
                selected_id=result.autotag.id,
            )
        )


class AutoTagFormView(LoginRequiredMixin, View):
    """Loads an autotag (or a blank create form) into the edit form.

    Used on table row clicks (existing autotag) and the New Auto Tag button (no
    autotag_id -> blank form).
    """

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, autotag_id=None):
        autotag = get_object_or_404(AutoTag, pk=autotag_id) if autotag_id else None
        accounts, prefills, entities = autotag_services.get_autotag_form_options()
        form_html = autotag_settings_helpers.render_autotag_form(
            accounts=accounts,
            prefills=prefills,
            entities=entities,
            autotag=autotag,
        )
        return HttpResponse(form_html)
