"""
Views for the Prefills Settings section.

Loaded as HTML fragments into the Settings shell:
- Prefills: config CRUD over Prefill (mirrors EntitySettingsView).
- Doc Searches: config CRUD over a prefill's DocSearch rows (nested, scoped by
  ``prefill_id`` — follows the LoanScheduleView nested precedent).

Views parse requests, call services for business logic, and call helpers for
rendering. No database writes and no HTML building here.
"""

from typing import Optional

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from api.forms import DocSearchForm, PrefillForm
from api.models import DocSearch, Prefill
from api.services import prefill_services
from api.views import prefill_settings_helpers


class PrefillSettingsView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def _render_content(
        self,
        prefill: Optional[Prefill] = None,
        change: Optional[str] = None,
        error: Optional[str] = None,
        form: Optional[PrefillForm] = None,
        selected_id: Optional[int] = None,
    ) -> str:
        """Builds the swappable Prefills fragment (header + table + form)."""
        prefill_form_html = prefill_settings_helpers.render_prefill_form(
            prefill=prefill,
            change=change,
            error=error,
            form=form,
        )
        prefills = prefill_services.get_prefills()
        return prefill_settings_helpers.render_prefills_content(
            prefills=prefills,
            prefill_form_html=prefill_form_html,
            selected_id=selected_id,
        )

    def get(self, request):
        return HttpResponse(self._render_content())

    def post(self, request, prefill_id=None):
        action = request.POST.get("action")

        if action == "clear":
            return HttpResponse(self._render_content())

        if action == "delete":
            result = prefill_services.delete_prefill(prefill_id)
            if result.success:
                return HttpResponse(self._render_content(change="delete"))
            return HttpResponse(
                self._render_content(
                    prefill=result.prefill,
                    error=result.error,
                    selected_id=result.prefill.id if result.prefill else None,
                )
            )

        if prefill_id:
            prefill = get_object_or_404(Prefill, pk=prefill_id)
            form = PrefillForm(request.POST, instance=prefill)
            change = "update"
        else:
            prefill = None
            form = PrefillForm(request.POST)
            change = "create"

        if not form.is_valid():
            return HttpResponse(
                self._render_content(
                    prefill=prefill,
                    form=form,
                    selected_id=prefill.id if prefill else None,
                )
            )

        result = prefill_services.save_prefill(form.cleaned_data, instance=prefill)
        if not result.success:
            return HttpResponse(
                self._render_content(
                    prefill=prefill,
                    form=form,
                    error=result.error,
                    selected_id=prefill.id if prefill else None,
                )
            )

        return HttpResponse(
            self._render_content(
                prefill=result.prefill,
                change=change,
                selected_id=result.prefill.id,
            )
        )


class PrefillFormView(LoginRequiredMixin, View):
    """Loads a prefill (or a blank create form) into the edit form.

    Used on table row clicks (existing prefill) and the New Prefill button (no
    prefill_id -> blank form).
    """

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, prefill_id=None):
        prefill = get_object_or_404(Prefill, pk=prefill_id) if prefill_id else None
        form_html = prefill_settings_helpers.render_prefill_form(prefill=prefill)
        return HttpResponse(form_html)


class DocSearchView(LoginRequiredMixin, View):
    """Renders a prefill's Doc Searches (GET) and applies create/edit/delete of
    a single Doc Search (POST), scoped to the parent prefill."""

    login_url = "/login/"
    redirect_field_name = "next"

    def _render_content(
        self,
        prefill: Prefill,
        doc_search: Optional[DocSearch] = None,
        change: Optional[str] = None,
        error: Optional[str] = None,
        form: Optional[DocSearchForm] = None,
        selected_id: Optional[int] = None,
    ) -> str:
        """Builds the swappable Doc Searches fragment for a prefill."""
        accounts, entities = prefill_services.get_docsearch_form_options()
        docsearch_form_html = prefill_settings_helpers.render_docsearch_form(
            prefill=prefill,
            accounts=accounts,
            entities=entities,
            doc_search=doc_search,
            change=change,
            error=error,
            form=form,
        )
        docsearches = prefill_services.get_docsearches(prefill.id)
        return prefill_settings_helpers.render_docsearches_content(
            prefill=prefill,
            docsearches=docsearches,
            docsearch_form_html=docsearch_form_html,
            selected_id=selected_id,
        )

    def get(self, request, prefill_id):
        prefill = get_object_or_404(Prefill, pk=prefill_id)
        return HttpResponse(self._render_content(prefill))

    def post(self, request, prefill_id, docsearch_id=None):
        prefill = get_object_or_404(Prefill, pk=prefill_id)
        action = request.POST.get("action")

        if action == "clear":
            return HttpResponse(self._render_content(prefill))

        if action == "delete":
            result = prefill_services.delete_docsearch(docsearch_id)
            if result.success:
                return HttpResponse(self._render_content(prefill, change="delete"))
            return HttpResponse(
                self._render_content(
                    prefill,
                    doc_search=result.doc_search,
                    error=result.error,
                    selected_id=(
                        result.doc_search.id if result.doc_search else None
                    ),
                )
            )

        if docsearch_id:
            doc_search = get_object_or_404(
                DocSearch, pk=docsearch_id, prefill=prefill
            )
            form = DocSearchForm(request.POST, instance=doc_search)
            change = "update"
        else:
            doc_search = None
            form = DocSearchForm(request.POST)
            change = "create"

        if not form.is_valid():
            return HttpResponse(
                self._render_content(
                    prefill,
                    doc_search=doc_search,
                    form=form,
                    selected_id=doc_search.id if doc_search else None,
                )
            )

        result = prefill_services.save_docsearch(
            prefill, form.cleaned_data, instance=doc_search
        )
        if not result.success:
            return HttpResponse(
                self._render_content(
                    prefill,
                    doc_search=doc_search,
                    form=form,
                    error=result.error,
                    selected_id=doc_search.id if doc_search else None,
                )
            )

        return HttpResponse(
            self._render_content(
                prefill,
                doc_search=result.doc_search,
                change=change,
                selected_id=result.doc_search.id,
            )
        )


class DocSearchFormView(LoginRequiredMixin, View):
    """Loads a Doc Search (or a blank create form) into the edit form.

    Used on row clicks (existing Doc Search) and the New Doc Search button (no
    docsearch_id -> blank form).
    """

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, prefill_id, docsearch_id=None):
        prefill = get_object_or_404(Prefill, pk=prefill_id)
        doc_search = (
            get_object_or_404(DocSearch, pk=docsearch_id, prefill=prefill)
            if docsearch_id
            else None
        )
        accounts, entities = prefill_services.get_docsearch_form_options()
        form_html = prefill_settings_helpers.render_docsearch_form(
            prefill=prefill,
            accounts=accounts,
            entities=entities,
            doc_search=doc_search,
        )
        return HttpResponse(form_html)
