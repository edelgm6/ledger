"""
Service layer for CSVProfile config CRUD (Settings page).

A CSVProfile maps a bank's CSV export columns onto Transaction fields so an
uploaded file can be imported (see ``CSVProfile.create_transactions_from_csv``).
This module exposes the list/create/update/delete operations the Settings UI
needs, delegating scalar writes to the shared ``crud`` helpers.

The novel piece vs. other single-model settings sections is the
``clear_values_column_pairs`` M2M (row-exclusion rules): the form submits a list
of ``(column, value)`` pairs, which ``_sync_pairs`` rewrites inside the save
transaction via ``crud.save_model``'s ``post_save`` hook.

Mirrors ``autotag_services`` (single-model config CRUD).
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction as db_transaction
from django.db.models import Count

from api.models import CSVColumnValuePair, CSVProfile
from api.services import crud


@dataclass
class CSVProfileResult:
    """Result of a CSV profile create/update/delete operation."""
    success: bool
    csv_profile: Optional[CSVProfile] = None
    error: Optional[str] = None


def get_csv_profiles() -> List[CSVProfile]:
    """Returns all CSV profiles ordered by name, annotated with the counts the
    list display renders (linked accounts and exclusion rules)."""
    return list(
        CSVProfile.objects.annotate(
            account_count=Count("accounts", distinct=True),
            exclusion_count=Count("clear_values_column_pairs", distinct=True),
        ).order_by("name")
    )


CSV_PROFILE_FIELDS = (
    "name",
    "date",
    "description",
    "category",
    "inflow",
    "outflow",
    "date_format",
    "clear_prepended_until_value",
)


def _sync_pairs(
    profile: CSVProfile, pairs: List[Tuple[str, str]]
) -> None:
    """Rewrites the profile's row-exclusion rules to exactly ``pairs``.

    The pairs are owned per-profile (created here, never shared), so the old
    linked rows are deleted before the new ones are created — this avoids
    orphan ``CSVColumnValuePair`` rows accumulating on every edit. Runs inside
    ``crud.save_model``'s atomic transaction.
    """
    profile.clear_values_column_pairs.all().delete()
    new_pairs = [
        CSVColumnValuePair(column=column, value=value)
        for column, value in pairs
    ]
    CSVColumnValuePair.objects.bulk_create(new_pairs)
    # The relation was just cleared, so add() skips the diff SELECT that set()
    # would run; an empty *new_pairs is a no-op.
    profile.clear_values_column_pairs.add(*new_pairs)


def save_csv_profile(
    cleaned_data: Dict[str, Any], instance: Optional[CSVProfile] = None
) -> CSVProfileResult:
    """Creates or updates a CSV profile from validated form data. ``instance``
    is the profile being edited (None to create). The row-exclusion rules in
    ``cleaned_data["column_value_pairs"]`` are synced after the scalar save."""
    pairs = cleaned_data.get("column_value_pairs", [])
    csv_profile, error = crud.save_model(
        CSVProfile,
        CSV_PROFILE_FIELDS,
        cleaned_data,
        instance,
        post_save=lambda profile: _sync_pairs(profile, pairs),
    )
    return CSVProfileResult(
        success=error is None, csv_profile=csv_profile, error=error
    )


def delete_csv_profile(csv_profile_id: int) -> CSVProfileResult:
    """Deletes a CSV profile by pk.

    ``Account.csv_profile`` is ``on_delete=PROTECT``, so a profile still linked
    to an account can't be deleted; the shared helper turns that ProtectedError
    into a friendly message naming the profile. The profile's row-exclusion rules
    (a plain M2M, owned per-profile) are deleted alongside it so they don't
    orphan — but only once the delete actually succeeds.
    """
    with db_transaction.atomic():
        pair_ids = list(
            CSVColumnValuePair.objects.filter(
                csvprofile=csv_profile_id
            ).values_list("id", flat=True)
        )
        csv_profile, error = crud.delete_model(
            CSVProfile,
            csv_profile_id,
            not_found="CSV profile not found.",
            protected=lambda profile: (
                f'Can\'t delete "{profile.name}" — it\'s still linked to an account.'
            ),
        )
        if error is None and pair_ids:
            CSVColumnValuePair.objects.filter(id__in=pair_ids).delete()

    return CSVProfileResult(
        success=error is None, csv_profile=csv_profile, error=error
    )
