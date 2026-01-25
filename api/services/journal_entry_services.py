from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from django.db import transaction as db_transaction
from django.db.models import QuerySet
from django.forms import BaseModelFormSet, modelformset_factory

from api.forms import BaseJournalEntryItemFormset, JournalEntryItemForm
from api.models import Account, Entity, JournalEntry, JournalEntryItem, Paystub, PaystubValue, Transaction


# Cached formset factory - created once at module load
_JournalEntryItemFormset = modelformset_factory(
    JournalEntryItem,
    formset=BaseJournalEntryItemFormset,
    form=JournalEntryItemForm,
)


def get_journal_entry_item_formset():
    """
    Returns the cached JournalEntryItem formset factory.

    Caches the factory at module level to avoid recreating it on every POST request.
    """
    return _JournalEntryItemFormset


def get_debits_and_credits(
    transaction: Transaction,
) -> Tuple[QuerySet[JournalEntryItem], QuerySet[JournalEntryItem]]:

    journal_entry = getattr(
        transaction, "journal_entry", None
    )  # Handle missing attribute

    if not journal_entry:
        return JournalEntryItem.objects.none(), JournalEntryItem.objects.none()

    journal_entry_items = JournalEntryItem.objects.filter(journal_entry=journal_entry)
    debits = journal_entry_items.filter(type=JournalEntryItem.JournalEntryType.DEBIT)
    credits = journal_entry_items.filter(type=JournalEntryItem.JournalEntryType.CREDIT)

    return debits, credits


def get_prefill_initial_data(
    transaction: Transaction,
    debits_initial_data: List[Dict[str, str | int]],
    credits_initial_data: List[Dict[str, str | int]],
) -> Tuple[List[Dict[str, str | int]], List[Dict[str, str | int]]]:

    prefill_items = (
        transaction.prefill.prefillitem_set.all()
        .select_related("account", "entity")
        .order_by("order")
    )
    for item in prefill_items:
        if item.journal_entry_item_type == JournalEntryItem.JournalEntryType.DEBIT:
            debits_initial_data.append(
                {
                    "account": item.account.name,
                    "amount": 0,
                    "entity": item.entity.name if item.entity else None,
                }
            )
        else:
            credits_initial_data.append(
                {
                    "account": item.account.name,
                    "amount": 0,
                    "entity": item.entity.name if item.entity else None,
                }
            )

    return debits_initial_data, credits_initial_data


def get_paystub_initial_data(
    paystub_id: int,
) -> Tuple[List[Dict[str, str | int]], List[Dict[str, str | int]]]:
    paystub_values = PaystubValue.objects.filter(paystub__pk=paystub_id).select_related(
        "account"
    )
    debits_initial_data = []
    credits_initial_data = []
    for paystub_value in paystub_values:
        if (
            paystub_value.journal_entry_item_type
            == JournalEntryItem.JournalEntryType.DEBIT
        ):
            debits_initial_data.append(
                {
                    "account": paystub_value.account.name,
                    "amount": paystub_value.amount,
                    "entity": paystub_value.entity,
                }
            )
        else:
            credits_initial_data.append(
                {
                    "account": paystub_value.account.name,
                    "amount": paystub_value.amount,
                    "entity": paystub_value.entity,
                }
            )

    return debits_initial_data, credits_initial_data


def get_initial_data(
    transaction: Transaction, paystub_id: Optional[int] = None
) -> Tuple[List[Dict[str, str | int]], List[Dict[str, str | int]]]:
    if paystub_id:
        return get_paystub_initial_data(paystub_id)

    if transaction.amount >= 0:
        transaction_account_is_debit = True
    else:
        transaction_account_is_debit = False

    debits_initial_data = []
    credits_initial_data = []

    transaction = Transaction.objects.select_related(
        "account", "suggested_account"
    ).get(pk=transaction.pk)

    primary_account, secondary_account = (
        (transaction.account, transaction.suggested_account)
        if transaction_account_is_debit
        else (transaction.suggested_account, transaction.account)
    )
    primary_entity, secondary_entity = (
        (transaction.account.entity, transaction.suggested_entity)
        if transaction_account_is_debit
        else (transaction.suggested_entity, transaction.account.entity)
    )

    debits_initial_data.append(
        {
            "account": getattr(primary_account, "name", None),
            "amount": abs(transaction.amount),
            "entity": primary_entity,
        }
    )

    credits_initial_data.append(
        {
            "account": getattr(secondary_account, "name", None),
            "amount": abs(transaction.amount),
            "entity": secondary_entity,
        }
    )

    if transaction.prefill:
        return get_prefill_initial_data(
            transaction=transaction,
            debits_initial_data=debits_initial_data,
            credits_initial_data=credits_initial_data,
        )

    return debits_initial_data, credits_initial_data


def get_entities_choices() -> Dict[str, int]:
    open_entities = Entity.objects.filter(is_closed=False).order_by("name")
    open_entities_choices = {entity.name: entity for entity in open_entities}
    return open_entities_choices


def get_accounts_choices() -> Dict[str, int]:
    open_accounts = Account.objects.filter(is_closed=False)
    open_accounts_choices = {account.name: account for account in open_accounts}
    return open_accounts_choices


def get_formsets(
    debits_initial_data: List[Dict[str, str | int]],
    credits_initial_data: List[Dict[str, str | int]],
    journal_entry_debits: QuerySet[JournalEntryItem],
    journal_entry_credits: QuerySet[JournalEntryItem],
    bound_debits_count: int,
    bound_credits_count: int,
) -> Tuple[BaseModelFormSet, BaseModelFormSet]:

    prefill_debits_count = len(debits_initial_data)
    prefill_credits_count = len(credits_initial_data)

    debit_formset = modelformset_factory(
        JournalEntryItem,
        form=JournalEntryItemForm,
        formset=BaseJournalEntryItemFormset,
        extra=max((10 - bound_debits_count), prefill_debits_count),
    )
    credit_formset = modelformset_factory(
        JournalEntryItem,
        form=JournalEntryItemForm,
        formset=BaseJournalEntryItemFormset,
        extra=max((10 - bound_credits_count), prefill_credits_count),
    )

    accounts_choices = get_accounts_choices()
    entities_choices = get_entities_choices()
    debit_formset = debit_formset(
        queryset=journal_entry_debits,
        initial=debits_initial_data,
        prefix="debits",
        form_kwargs={
            "open_accounts_choices": accounts_choices,
            "open_entities_choices": entities_choices,
        },
    )
    credit_formset = credit_formset(
        queryset=journal_entry_credits,
        initial=credits_initial_data,
        prefix="credits",
        form_kwargs={
            "open_accounts_choices": accounts_choices,
            "open_entities_choices": entities_choices,
        },
    )

    return debit_formset, credit_formset


# New service functions for business logic


@dataclass
class ValidationResult:
    """Result of journal entry validation."""
    is_valid: bool
    errors: List[str]


def validate_journal_entry_balance(
    transaction: Transaction,
    debits_data: List[dict],
    credits_data: List[dict]
) -> ValidationResult:
    """
    Validates journal entry business rules:
    - Debits total equals credits total
    - Exactly one item matches transaction account/amount

    Returns ValidationResult with errors if invalid.
    """
    errors = []

    # Calculate totals
    debit_total = sum(item.get('amount', 0) for item in debits_data if item.get('amount'))
    credit_total = sum(item.get('amount', 0) for item in credits_data if item.get('amount'))

    # Check balance
    if debit_total != credit_total:
        errors.append(f"Debits (${debit_total}) and Credits (${credit_total}) must balance.")

    # Check transaction match
    formset_data = debits_data if transaction.amount >= 0 else credits_data
    matching_items = [
        item for item in formset_data
        if item.get('amount') == abs(transaction.amount)
        and item.get('account') == transaction.account
    ]

    if len(matching_items) != 1:
        errors.append("Must be one journal entry item with the Transaction's account and amount.")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)


@dataclass
class SaveResult:
    """Result of journal entry save operation."""
    success: bool
    journal_entry: Optional[JournalEntry]
    error: Optional[str] = None


@db_transaction.atomic
def save_journal_entry(
    transaction_obj: Transaction,
    debits_data: List[dict],
    credits_data: List[dict],
    paystub_id: Optional[int] = None
) -> SaveResult:
    """
    Saves journal entry with all items atomically.

    Steps:
    1. Create JournalEntry if doesn't exist
    2. Classify items as new vs existing
    3. Bulk update existing items
    4. Bulk create new items
    5. Close transaction
    6. Link paystub if provided

    All operations wrapped in atomic transaction.
    Returns SaveResult with journal_entry on success.
    """
    try:
        # 1. Get or create JournalEntry
        try:
            journal_entry = transaction_obj.journal_entry
        except JournalEntry.DoesNotExist:
            journal_entry = JournalEntry.objects.create(
                date=transaction_obj.date,
                transaction=transaction_obj
            )

        # 2. Process debits and credits
        new_items = []
        changed_items = []

        for item_data in debits_data:
            item = _create_journal_entry_item(
                journal_entry=journal_entry,
                item_data=item_data,
                entry_type=JournalEntryItem.JournalEntryType.DEBIT
            )
            if item:
                (changed_items if item.pk else new_items).append(item)

        for item_data in credits_data:
            item = _create_journal_entry_item(
                journal_entry=journal_entry,
                item_data=item_data,
                entry_type=JournalEntryItem.JournalEntryType.CREDIT
            )
            if item:
                (changed_items if item.pk else new_items).append(item)

        # 3. Bulk operations
        if changed_items:
            JournalEntryItem.objects.bulk_update(
                changed_items,
                ['amount', 'account', 'entity']
            )

        if new_items:
            JournalEntryItem.objects.bulk_create(new_items)

        # 4. Close transaction
        transaction_obj.close()

        # 5. Link paystub if provided
        if paystub_id:
            try:
                paystub = Paystub.objects.get(pk=paystub_id)
                paystub.journal_entry = journal_entry
                paystub.save()
            except (Paystub.DoesNotExist, ValueError):
                pass  # Paystub linking is optional

        return SaveResult(success=True, journal_entry=journal_entry)

    except Exception as e:
        # Transaction will rollback automatically
        return SaveResult(success=False, journal_entry=None, error=str(e))


def _create_journal_entry_item(
    journal_entry: JournalEntry,
    item_data: dict,
    entry_type: str
) -> Optional[JournalEntryItem]:
    """
    Helper to create JournalEntryItem from cleaned form data.
    Returns None if item has no amount (empty form).
    """
    amount = item_data.get('amount')
    if not amount:
        return None

    # Get existing item by ID, or create new one
    item_id = item_data.get('id')
    if item_id:
        item = JournalEntryItem.objects.get(pk=item_id)
    else:
        item = JournalEntryItem(journal_entry=journal_entry, type=entry_type)

    # Update fields
    item.amount = amount
    item.account = item_data.get('account')
    item.entity = item_data.get('entity')

    return item


@dataclass
class PostSaveContext:
    """Context for rendering after successful save."""
    transactions: List[Transaction]
    highlighted_index: int
    highlighted_transaction: Optional[Transaction]
    created_entities: List[Entity]


def get_post_save_context(
    filter_form,
    current_index: int,
    debit_formset,
    credit_formset
) -> PostSaveContext:
    """
    Builds context for rendering after successful save.

    Handles:
    - Getting filtered transactions
    - Determining next transaction to highlight
    - Extracting entities created during form cleaning
    """
    if filter_form.is_valid():
        transactions = list(filter_form.get_transactions())
    else:
        # Fallback to default filter
        transactions = list(Transaction.objects.filter(
            is_closed=False,
            type__in=[
                Transaction.TransactionType.INCOME,
                Transaction.TransactionType.PURCHASE
            ]
        ))

    # Get next transaction (handle index out of bounds)
    if not transactions:
        return PostSaveContext(
            transactions=[],
            highlighted_index=0,
            highlighted_transaction=None,
            created_entities=[]
        )

    try:
        highlighted_transaction = transactions[current_index]
        highlighted_index = current_index
    except IndexError:
        highlighted_transaction = transactions[0]
        highlighted_index = 0

    # Extract created entities from formsets
    created_entities = []
    for formset in [debit_formset, credit_formset]:
        for form in formset:
            if hasattr(form, 'created_entity'):
                created_entities.append(form.created_entity)

    return PostSaveContext(
        transactions=transactions,
        highlighted_index=highlighted_index,
        highlighted_transaction=highlighted_transaction,
        created_entities=created_entities
    )


def apply_autotags_to_open_transactions() -> int:
    """
    Applies autotags to all open transactions.
    Returns count of updated transactions.
    """
    open_transactions = Transaction.objects.filter(is_closed=False)
    Transaction.apply_autotags(open_transactions)
    open_transactions.bulk_update(
        open_transactions,
        ["suggested_account", "prefill", "type", "suggested_entity"],
    )
    return open_transactions.count()
