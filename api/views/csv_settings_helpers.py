"""
Helper functions for rendering the CSV Profiles Settings section.

Pure functions that take data and return HTML strings via ``render_to_string``.
No database writes and no business logic. Mirrors ``autotag_settings_helpers``.
"""

from typing import Any, Dict, List, Optional

from django.template.loader import render_to_string

from api.forms import CSVProfileForm, parse_pair_rows
from api.models import CSVProfile
from api.views.form_helpers import resolve_form_values

TEXT_FIELDS = (
    "name",
    "date",
    "description",
    "category",
    "inflow",
    "outflow",
    "date_format",
    "clear_prepended_until_value",
)


def render_csv_profiles_content(
    csv_profiles: List[CSVProfile],
    csv_profile_form_html: str,
    selected_id: Optional[int] = None,
) -> str:
    """Combines header + table + form into the swappable CSV Profiles fragment."""
    return render_to_string(
        "api/content/csv-profiles-content.html",
        {
            "csv_profiles": csv_profiles,
            "total": len(csv_profiles),
            "selected_id": selected_id,
            "csv_profile_form": csv_profile_form_html,
        },
    )


def _resolve_pairs(
    csv_profile: Optional[CSVProfile], form: Optional[CSVProfileForm]
) -> List[Dict[str, str]]:
    """Builds the row-exclusion pairs to pre-fill the inline editor.

    On a bound (usually invalid) form, echo what the user submitted so a
    validation error doesn't wipe their rows; otherwise read the profile's saved
    pairs; a blank-create form gets none.
    """
    if form is not None and form.is_bound:
        return parse_pair_rows(form.data)

    if csv_profile is not None:
        return [
            {"column": pair.column, "value": pair.value}
            for pair in csv_profile.clear_values_column_pairs.all()
        ]

    return []


def render_csv_profile_form(
    csv_profile: Optional[CSVProfile] = None,
    change: Optional[str] = None,
    error: Optional[str] = None,
    form: Optional[CSVProfileForm] = None,
) -> str:
    """Renders the CSV profile add/edit form HTML."""
    context: Dict[str, Any] = {
        "csv_profile": csv_profile,
        "change": change,
        "error": error,
        "form": form,
        "values": resolve_form_values(
            csv_profile,
            form,
            text=TEXT_FIELDS,
            booleans=("positive_outflows",),
            defaults={"date_format": "%Y-%m-%d"},
        ),
        "pairs": _resolve_pairs(csv_profile, form),
    }
    return render_to_string("api/entry_forms/csv-profile-form.html", context)
