"""
Helper functions for rendering the recharacterization chat HTML.

Pure functions: take data, return HTML strings. No DB writes, no HTTP objects.
"""

from typing import Dict, List, Optional

from django.template.loader import render_to_string

from api.services.recharacterize_services import PlanPreview


def render_main(
    messages: List[Dict[str, str]],
    preview: Optional[PlanPreview] = None,
    flash: Optional[str] = None,
) -> str:
    """Renders the swappable #recharacterize-main region (chat + preview)."""
    return render_to_string(
        "api/components/recharacterize-main.html",
        {"messages": messages, "preview": preview, "flash": flash},
    )


def render_page(
    messages: List[Dict[str, str]],
    preview: Optional[PlanPreview] = None,
    flash: Optional[str] = None,
) -> str:
    """Renders the full-page content fragment (heading + main region)."""
    return render_to_string(
        "api/views/recharacterize.html",
        {"main": render_main(messages, preview, flash)},
    )
