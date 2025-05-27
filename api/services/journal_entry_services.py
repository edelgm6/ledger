from typing import Dict, List, Optional, Tuple

from django.db.models import QuerySet
from django.forms import BaseModelFormSet, modelformset_factory
from django.template.loader import render_to_string

from api.forms import BaseJournalEntryItemFormset, JournalEntryItemForm
from api.models import Account, Entity, JournalEntryItem, PaystubValue, Transaction


def transaction_account_is_debit(transaction):
    # Determine if transaction's source account is a debit
    if transaction.amount >= 0:
        transaction_account_is_debit = True
    else:
        transaction_account_is_debit = False

    return transaction_account_is_debit


def get_debits_and_credits(
    transaction: Transaction,
) -> Tuple[QuerySet[JournalEntryItem], QuerySet[JournalEntryItem], bool]:
    journal_entry = getattr(
        transaction, "journal_entry", None
    )  # Handle missing attribute

    if not journal_entry:
        return JournalEntryItem.objects.none(), JournalEntryItem.objects.none(), False

    journal_entry_items = JournalEntryItem.objects.filter(journal_entry=journal_entry)
    debits = journal_entry_items.filter(type=JournalEntryItem.JournalEntryType.DEBIT)
    credits = journal_entry_items.filter(type=JournalEntryItem.JournalEntryType.CREDIT)

    return debits, credits, True


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
                    "entity": item.entity.name,
                }
            )
        else:
            credits_initial_data.append(
                {
                    "account": item.account.name,
                    "amount": 0,
                    "entity": item.entity.name,
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
    # If submitting along with a paystub, skip everthing and return
    # the paystub prefill
    if paystub_id:
        return get_paystub_initial_data(paystub_id)

    transaction = Transaction.objects.select_related(
        "account", "suggested_account"
    ).get(pk=transaction.pk)

    debits_initial_data = []
    credits_initial_data = []

    # Determine whether to put the transaction account on the debit
    # or credit side, same with the entity
    transaction_is_debit = transaction_account_is_debit(transaction)
    primary_account, secondary_account = (
        (transaction.account, transaction.suggested_account)
        if transaction_is_debit
        else (transaction.suggested_account, transaction.account)
    )
    primary_entity, secondary_entity = (
        (transaction.account.entity, transaction.suggested_entity)
        if transaction_is_debit
        else (transaction.suggested_entity, transaction.account.entity)
    )

    # Set the initial data for the debit and credit form based on the
    # primary and secondary accounts
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

    # If there's a transaction prefill, send initial data
    # so far and add to it via the prefill
    if transaction.prefill:
        return get_prefill_initial_data(
            transaction=transaction,
            debits_initial_data=debits_initial_data,
            credits_initial_data=credits_initial_data,
        )

    return debits_initial_data, credits_initial_data


def convert_frontend_list_to_python(frontend_list: str) -> List[int]:
    python_list = [int(id) for id in frontend_list.split(",")]
    return python_list


def get_transaction_store_to_html(
    transaction_ids: List[int], swap_oob: bool = False
) -> str:
    html = render_to_string(
        "api/components/transaction-store.html",
        {"transaction_ids": transaction_ids, "swap_oob": swap_oob},
    )

    return html


def _get_next_id(ids_list: List[int], transaction_id: str) -> Optional[int]:
    print(list(ids_list))
    print(transaction_id)
    idx = list(ids_list).index(int(transaction_id))
    next_id = ids_list[idx + 1] if idx + 1 < len(ids_list) else None
    return next_id


def get_journal_entry_form_html(transaction, transaction_ids):
    journal_entry_debits, journal_entry_credits, has_debits_or_credits = (
        get_debits_and_credits(transaction)
    )

    debits_initial_data = []
    credits_initial_data = []
    if not has_debits_or_credits:
        debits_initial_data, credits_initial_data = get_initial_data(
            transaction=transaction
        )

    debit_formset, credit_formset = get_formsets(
        debits_initial_data=debits_initial_data,
        credits_initial_data=credits_initial_data,
        journal_entry_debits=journal_entry_debits,
        journal_entry_credits=journal_entry_credits,
    )

    # Set the total amounts for the debit and credits
    debit_prefilled_total = debit_formset.get_entry_total()
    credit_prefilled_total = credit_formset.get_entry_total()
    context = {
        "debit_formset": debit_formset,
        "credit_formset": credit_formset,
        "transaction_id": transaction.id,
        "next_transaction_id": _get_next_id(
            ids_list=transaction_ids, transaction_id=transaction.id
        ),
        "transaction_ids": transaction_ids,
        "autofocus_debit": transaction_account_is_debit(transaction),
        "debit_prefilled_total": debit_prefilled_total,
        "credit_prefilled_total": credit_prefilled_total,
    }

    template = "api/entry_forms/journal-entry-button.html"
    return render_to_string(template, context)


def get_entities_choices() -> Dict[str, Entity]:
    open_entities = Entity.objects.filter(is_closed=False).order_by("name")
    open_entities_choices = {entity.name: entity for entity in open_entities}
    return open_entities_choices


def get_accounts_choices() -> Dict[str, Account]:
    open_accounts = Account.objects.filter(is_closed=False)
    open_accounts_choices = {account.name: account for account in open_accounts}
    return open_accounts_choices


def get_formsets(
    debits_initial_data: List[Dict[str, str | int]],
    credits_initial_data: List[Dict[str, str | int]],
    journal_entry_debits: QuerySet[JournalEntryItem],
    journal_entry_credits: QuerySet[JournalEntryItem],
) -> Tuple[BaseModelFormSet, BaseModelFormSet]:
    # Need counts to figure out how long the formset should be
    prefill_debits_count = len(debits_initial_data)
    prefill_credits_count = len(credits_initial_data)
    max_prefills_count = max(prefill_debits_count, prefill_credits_count)

    bound_debits_count = journal_entry_debits.count()
    bound_credits_count = journal_entry_credits.count()

    debit_formset = modelformset_factory(
        JournalEntryItem,
        form=JournalEntryItemForm,
        formset=BaseJournalEntryItemFormset,
        extra=max((10 - bound_debits_count), max_prefills_count),
    )
    credit_formset = modelformset_factory(
        JournalEntryItem,
        form=JournalEntryItemForm,
        formset=BaseJournalEntryItemFormset,
        extra=max((10 - bound_credits_count), max_prefills_count),
    )

    # If journal_entry_debits or journal_entry_cresits
    # are not None, they'll be bound to the formset. Else
    # will use initial data
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
