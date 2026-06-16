"""
Account service layer for business logic and database operations.

All account-related business logic and database writes go through these service
functions. Services are pure functions with no HTTP dependencies and return
dataclass result objects.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import QuerySet

from api.models import Account, CSVProfile, Entity
from api.services import crud


@dataclass
class AccountResult:
    """Result of an account create/update/delete operation."""
    success: bool
    account: Optional[Account] = None
    error: Optional[str] = None


def get_accounts() -> List[Account]:
    """Returns all accounts, open ones first, then alphabetical by name."""
    return list(
        Account.objects.select_related("entity").order_by("is_closed", "name")
    )


def get_account_form_options() -> Tuple[QuerySet, QuerySet]:
    """Returns the (entities, csv_profiles) querysets used to populate the
    account edit form's dropdowns."""
    entities = Entity.objects.order_by("name")
    csv_profiles = CSVProfile.objects.order_by("name")
    return entities, csv_profiles


ACCOUNT_FIELDS = (
    "name",
    "type",
    "sub_type",
    "entity",
    "csv_profile",
    "is_closed",
    "is_depreciation",
)


def save_account(
    cleaned_data: Dict[str, Any], instance: Optional[Account] = None
) -> AccountResult:
    """Creates or updates an account from validated form data.

    The caller (view) validates the form and passes ``form.cleaned_data``;
    ``instance`` is the account being edited (None to create). Returns an
    AccountResult; on any DB error the transaction rolls back.
    """
    account, error = crud.save_model(Account, ACCOUNT_FIELDS, cleaned_data, instance)
    return AccountResult(success=error is None, account=account, error=error)


def delete_account(account_id: int) -> AccountResult:
    """Deletes an account, gracefully blocking when it is still referenced.

    Accounts are PROTECT-referenced by transactions, journal entry items,
    paystub values, amortizations, etc. Rather than 500ing on a ProtectedError,
    we return a friendly message so the UI can display it inline.
    """
    account, error = crud.delete_model(
        Account,
        account_id,
        not_found="Account not found.",
        protected=lambda a: (
            f"Can't delete '{a.name}' — it's still used by other "
            "records (transactions, journal entries, paystub values, etc.). "
            "Close it instead to archive it."
        ),
    )
    return AccountResult(success=error is None, account=account, error=error)
