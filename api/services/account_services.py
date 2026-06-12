"""
Account service layer for business logic and database operations.

All account-related business logic and database writes go through these service
functions. Services are pure functions with no HTTP dependencies and return
dataclass result objects.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction as db_transaction
from django.db.models import ProtectedError, QuerySet

from api.models import Account, CSVProfile, Entity


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


@db_transaction.atomic
def save_account(
    cleaned_data: Dict[str, Any], instance: Optional[Account] = None
) -> AccountResult:
    """Creates or updates an account from validated form data.

    The caller (view) validates the form and passes ``form.cleaned_data``;
    ``instance`` is the account being edited (None to create). Returns an
    AccountResult; on any DB error the transaction rolls back.
    """
    try:
        account = instance or Account()
        for field in ACCOUNT_FIELDS:
            setattr(account, field, cleaned_data.get(field))
        account.save()
        return AccountResult(success=True, account=account)
    except Exception as e:  # pragma: no cover - defensive
        return AccountResult(success=False, error=str(e))


def delete_account(account_id: int) -> AccountResult:
    """Deletes an account, gracefully blocking when it is still referenced.

    Accounts are PROTECT-referenced by transactions, journal entry items,
    paystub values, amortizations, etc. Rather than 500ing on a ProtectedError,
    we return a friendly message so the UI can display it inline.
    """
    try:
        account = Account.objects.get(pk=account_id)
    except Account.DoesNotExist:
        return AccountResult(success=False, error="Account not found.")

    try:
        account.delete()
        return AccountResult(success=True, account=account)
    except ProtectedError:
        return AccountResult(
            success=False,
            account=account,
            error=(
                f"Can't delete '{account.name}' — it's still used by other "
                "records (transactions, journal entries, paystub values, etc.). "
                "Close it instead to archive it."
            ),
        )
