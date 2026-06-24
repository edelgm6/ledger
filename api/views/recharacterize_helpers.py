"""
Helper functions for rendering the recharacterization chat HTML.

Pure functions: take data, return HTML strings. No DB writes, no HTTP objects.
"""

from typing import Dict, List, Optional

from django.template.loader import render_to_string

from api.services.recharacterize_services import PlanPreview
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
) -> str:
    """Renders the swappable #recharacterize-main region (chat + preview)."""
    return render_to_string(
        "api/components/recharacterize-main.html",
        {"messages": messages, "preview": preview, "flash": flash, "error": error},
    )


def render_page(
    messages: List[Dict[str, str]],
    preview: Optional[PlanPreview] = None,
    flash: Optional[str] = None,
    error: Optional[Dict[str, str]] = None,
) -> str:
    """Renders the full-page content fragment (heading + main region)."""
    return render_to_string(
        "api/views/recharacterize.html",
        {"main": render_main(messages, preview, flash, error)},
    )
