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
from api.views.settings_crud import SettingsCrudView


class EntitySettingsView(SettingsCrudView):
    noun = "entity"
    model = Entity
    form_class = EntityForm
    pk_url_kwarg = "entity_id"

    def save(self, cleaned_data, instance):
        return entity_services.save_entity(cleaned_data, instance=instance)

    def delete(self, pk):
        return entity_services.delete_entity(pk)

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
