from decimal import Decimal
from typing import Any, Dict, List

from django.db import transaction as db_transaction

from api.models import Account, Entity, JournalEntryItem, Transaction
from api.services.journal_entry_services import (
    SaveResult,
    validate_journal_entry_balance,
    save_journal_entry,
)


def resolve_names_to_objects(
    items_data: List[Dict[str, Any]],
    accounts_map: Dict[str, Account],
    entities_map: Dict[str, Entity],
    created_entities: List[str],
) -> List[Dict[str, Any]]:
    """
    Resolves account/entity name strings to model objects.
    Auto-creates entities that don't exist.

    Returns list of dicts with 'account' (Account), 'amount' (Decimal),
    and optionally 'entity' (Entity).
    """
    resolved = []
    for item in items_data:
        account_name = item["account"]
        account = accounts_map.get(account_name)
        if not account:
            raise ValueError(f"Account '{account_name}' not found.")

        resolved_item = {
            "account": account,
            "amount": Decimal(str(item["amount"])),
        }

        entity_name = item.get("entity")
        if entity_name:
            entity = entities_map.get(entity_name)
            if not entity:
                entity = Entity.objects.create(name=entity_name)
                entities_map[entity_name] = entity
                created_entities.append(entity_name)
            resolved_item["entity"] = entity

        resolved.append(resolved_item)
    return resolved


def _create_one_journal_entry(
    transaction_id: int,
    debits_data: List[Dict[str, Any]],
    credits_data: List[Dict[str, Any]],
    created_by: str,
    accounts_map: Dict[str, Account],
    entities_map: Dict[str, Entity],
    created_entities: List[str],
    error_prefix: str = "",
) -> Dict[str, Any]:
    """The six steps both API entry points share: look up the transaction,
    resolve names to objects, validate the balance, save.

    ``error_prefix`` is applied to the validation and save failures only. The
    not-found and already-closed messages already name the transaction, so the
    bulk path does not prefix them -- preserving both paths' exact wording.

    Raises ValueError on any failure so the caller's atomic block rolls back.
    """
    try:
        transaction_obj = Transaction.objects.select_related("account").get(
            pk=transaction_id
        )
    except Transaction.DoesNotExist:
        raise ValueError(f"Transaction {transaction_id} not found.")

    if transaction_obj.is_closed:
        raise ValueError(f"Transaction {transaction_id} is already closed.")

    resolved_debits = resolve_names_to_objects(
        debits_data, accounts_map, entities_map, created_entities
    )
    resolved_credits = resolve_names_to_objects(
        credits_data, accounts_map, entities_map, created_entities
    )

    validation = validate_journal_entry_balance(
        transaction=transaction_obj,
        debits_data=resolved_debits,
        credits_data=resolved_credits,
    )
    if not validation.is_valid:
        raise ValueError(f"{error_prefix}{'; '.join(validation.errors)}")

    result: SaveResult = save_journal_entry(
        transaction_obj=transaction_obj,
        debits_data=resolved_debits,
        credits_data=resolved_credits,
        created_by=created_by,
    )
    if not result.success:
        raise ValueError(f"{error_prefix}{result.error}")

    return {
        "journal_entry_id": result.journal_entry.id,
        "transaction_id": transaction_id,
        "created_by": created_by,
    }


@db_transaction.atomic
def create_journal_entry_from_api(
    transaction_id: int,
    debits_data: List[Dict[str, Any]],
    credits_data: List[Dict[str, Any]],
    created_by: str = "user",
) -> Dict[str, Any]:
    """
    Creates a single journal entry from API input.

    Atomic: resolve_names_to_objects auto-creates unrecognised entities, so
    without this an entry rejected for being unbalanced still committed those
    rows -- the request was refused but the ledger had changed.

    Returns dict with journal_entry_id, transaction_id, created_by, created_entities.
    """
    accounts_map = {a.name: a for a in Account.objects.all()}
    entities_map = {e.name: e for e in Entity.objects.all()}
    created_entities: List[str] = []

    result = _create_one_journal_entry(
        transaction_id=transaction_id,
        debits_data=debits_data,
        credits_data=credits_data,
        created_by=created_by,
        accounts_map=accounts_map,
        entities_map=entities_map,
        created_entities=created_entities,
    )
    return {**result, "created_entities": created_entities}


@db_transaction.atomic
def bulk_create_journal_entries(
    entries_data: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Creates multiple journal entries atomically (all-or-nothing).

    Pre-fetches account/entity maps once for the batch.
    Raises ValueError on any failure to trigger rollback.
    """
    accounts_map = {a.name: a for a in Account.objects.all()}
    entities_map = {e.name: e for e in Entity.objects.all()}
    all_created_entities: List[str] = []
    results = []

    for entry_data in entries_data:
        transaction_id = entry_data["transaction_id"]
        results.append(
            _create_one_journal_entry(
                transaction_id=transaction_id,
                debits_data=entry_data["debits"],
                credits_data=entry_data["credits"],
                created_by=entry_data.get("created_by", "user"),
                accounts_map=accounts_map,
                entities_map=entities_map,
                created_entities=all_created_entities,
                error_prefix=f"Transaction {transaction_id}: ",
            )
        )

    return {
        "count": len(results),
        "journal_entries": results,
        "created_entities": all_created_entities,
    }
