"""
Views for the Entities Settings section.

Loaded as an HTML fragment into the Settings shell. Provides config CRUD over
the Entity model (mirrors BillRulesView/Accounts).

Views parse requests, call services for business logic, and call helpers for
rendering. No database writes and no HTML building here.
"""

from typing import Optional

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views import View

from api.forms import EntityForm
from api.models import Entity
from api.services import entity_services
from api.views import entity_settings_helpers


class EntitySettingsView(LoginRequiredMixin, View):
    login_url = "/login/"
    redirect_field_name = "next"

    def _render_content(
        self,
        entity: Optional[Entity] = None,
        change: Optional[str] = None,
        error: Optional[str] = None,
        form: Optional[EntityForm] = None,
        selected_id: Optional[int] = None,
    ) -> str:
        """Builds the swappable Entities fragment (header + table + form)."""
        entity_form_html = entity_settings_helpers.render_entity_form(
            entity=entity,
            change=change,
            error=error,
            form=form,
        )
        entities = entity_services.get_entities()
        return entity_settings_helpers.render_entities_content(
            entities=entities,
            entity_form_html=entity_form_html,
            selected_id=selected_id,
        )

    def get(self, request):
        return HttpResponse(self._render_content())

    def post(self, request, entity_id=None):
        action = request.POST.get("action")

        if action == "clear":
            return HttpResponse(self._render_content())

        if action == "delete":
            result = entity_services.delete_entity(entity_id)
            if result.success:
                return HttpResponse(self._render_content(change="delete"))
            return HttpResponse(
                self._render_content(
                    entity=result.entity,
                    error=result.error,
                    selected_id=result.entity.id if result.entity else None,
                )
            )

        if entity_id:
            entity = get_object_or_404(Entity, pk=entity_id)
            form = EntityForm(request.POST, instance=entity)
            change = "update"
        else:
            entity = None
            form = EntityForm(request.POST)
            change = "create"

        if not form.is_valid():
            return HttpResponse(
                self._render_content(
                    entity=entity,
                    form=form,
                    selected_id=entity.id if entity else None,
                )
            )

        result = entity_services.save_entity(form.cleaned_data, instance=entity)
        if not result.success:
            return HttpResponse(
                self._render_content(
                    entity=entity,
                    form=form,
                    error=result.error,
                    selected_id=entity.id if entity else None,
                )
            )

        return HttpResponse(
            self._render_content(
                entity=result.entity,
                change=change,
                selected_id=result.entity.id,
            )
        )


class EntityFormView(LoginRequiredMixin, View):
    """Loads an entity (or a blank create form) into the edit form.

    Used on table row clicks (existing entity) and the New Entity button (no
    entity_id -> blank form).
    """

    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request, entity_id=None):
        entity = get_object_or_404(Entity, pk=entity_id) if entity_id else None
        form_html = entity_settings_helpers.render_entity_form(entity=entity)
        return HttpResponse(form_html)
