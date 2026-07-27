"""
Helper functions for rendering the recharacterization HTML.

Pure functions: take data, return HTML strings. No DB writes, no HTTP objects.
"""

from typing import List, Optional

from django.template.loader import render_to_string

from api.models import RecharacterizeChange
from api.services.recharacterize_services import PageResult, PlanPreview


def render_main(
    preview: Optional[PlanPreview] = None,
    flash: Optional[str] = None,
    flash_error: Optional[str] = None,
    history: Optional[List[RecharacterizeChange]] = None,
    *,
    manual_form=None,
    edit_index: Optional[int] = None,
) -> str:
    """Renders the swappable #recharacterize-main region (builder + preview + history).

    ``manual_form`` is the builder form (it supplies the account/entity and
    action-target select options and carries field errors back on invalid submit).
    ``edit_index`` (when set) puts the builder in edit mode, overwriting that
    operation rather than appending. ``flash`` / ``flash_error`` surface an
    apply/revert outcome above the preview.
    """
    return render_to_string(
        "api/components/recharacterize-main.html",
        {
            "preview": preview,
            "flash": flash,
            "flash_error": flash_error,
            "history": history or [],
            "manual_form": manual_form,
            "edit_index": edit_index,
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
