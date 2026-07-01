"""
Helper functions for rendering the recharacterization chat HTML.

Pure functions: take data, return HTML strings. No DB writes, no HTTP objects.
"""

from typing import Dict, List, Optional

from django.template.loader import render_to_string

from api.models import RecharacterizeChange
from api.services.recharacterize_services import PageResult, PlanPreview
from api.utils import friendly_error_message, short_error_label


def build_turn_error(error_message: Optional[str]) -> Optional[Dict[str, str]]:
    """Assembles the template context for a failed Gemini turn.

    Returns None when there is no error. Otherwise a dict with a compact
    ``label`` (badge), a recovery-oriented ``message``, and the full ``detail``
    for a tooltip — mirroring the paystub/bill failure surface.
    """
    if not error_message:
        return None
    return {
        "label": short_error_label(error_message),
        "message": friendly_error_message(error_message),
        "detail": error_message,
    }


def render_main(
    messages: List[Dict[str, str]],
    preview: Optional[PlanPreview] = None,
    flash: Optional[str] = None,
    error: Optional[Dict[str, str]] = None,
    history: Optional[List[RecharacterizeChange]] = None,
    active_tab: str = "agent",
    manual_form=None,
    edit_index: Optional[int] = None,
    edit_agent_error: Optional[str] = None,
) -> str:
    """Renders the swappable #recharacterize-main region (chat + preview + history).

    ``active_tab`` decides which tab (agent vs. manual) is open after an htmx
    swap; ``manual_form`` is the builder form (it supplies the account/entity and
    action-target select options and carries field errors back on invalid submit).
    ``edit_index`` (when set) puts the manual builder in edit mode, overwriting that
    operation rather than appending.
    """
    return render_to_string(
        "api/components/recharacterize-main.html",
        {
            "messages": messages,
            "preview": preview,
            "flash": flash,
            "error": error,
            "history": history or [],
            "active_tab": active_tab,
            "manual_form": manual_form,
            "edit_index": edit_index,
            "edit_agent_error": edit_agent_error,
        },
    )


def render_affected_page(page: Optional[PageResult]) -> str:
    """Renders the swappable, paginated table region for one operation."""
    return render_to_string(
        "api/tables/recharacterize-affected-page.html",
        {"page": page},
    )


def render_page(main: str) -> str:
    """Wraps an already-rendered main region in the full-page shell.

    The caller renders the main region through the views' single seam, so this
    only adds the page heading around it.
    """
    return render_to_string("api/views/recharacterize.html", {"main": main})
