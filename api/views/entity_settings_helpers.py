"""
Helper functions for rendering the Entities Settings section (entity config
CRUD).

These pure functions take data and return HTML strings via render_to_string.
They contain no database writes and no business logic. Mirrors
bill_settings_helpers.
"""

from typing import List, Optional

from django.template.loader import render_to_string

from api.forms import EntityForm
from api.models import Entity
from api.views.form_helpers import resolve_form_values


def render_entities_content(
    entities: List[Entity],
    entity_form_html: str,
    selected_id: Optional[int] = None,
) -> str:
    """Combines the header + table + form into the swappable Entities fragment."""
    return render_to_string(
        "api/content/entities-content.html",
        {
            "entities": entities,
            "total": len(entities),
            "selected_id": selected_id,
            "entity_form": entity_form_html,
        },
    )


def render_entity_form(
    entity: Optional[Entity] = None,
    change: Optional[str] = None,
    error: Optional[str] = None,
    form: Optional[EntityForm] = None,
) -> str:
    """Renders the entity add/edit form HTML.

    Args:
        entity: Existing entity being edited (None for the create form).
        change: Type of change just performed ("create"/"update"/"delete").
        error: A friendly error message to display inline (e.g. delete blocked).
        form: A bound form carrying validation errors to redisplay.
    """
    context = {
        "entity": entity,
        "change": change,
        "error": error,
        "form": form,
        "values": resolve_form_values(
            entity, form, text=("name",), booleans=("is_closed",)
        ),
    }
    return render_to_string("api/entry_forms/entity-form.html", context)
