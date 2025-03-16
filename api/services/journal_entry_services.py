from typing import Dict, List, Optional, Tuple

from django.db.models import QuerySet
from django.forms import BaseModelFormSet, modelformset_factory

from api.forms import BaseJournalEntryItemFormset, JournalEntryItemForm
from api.models import Account, Entity, JournalEntryItem, PaystubValue, Transaction


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
