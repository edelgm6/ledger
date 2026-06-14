"""
Business logic for utility-bill ingestion, account resolution, and matching
ingested bills to uploaded bank transactions.

All DB writes for the bill feature live here (per the service-layer pattern).
"""
import logging
import re
from collections import defaultdict
from typing import Iterable, List, Optional

from django.db import transaction as db_transaction

from api.models import Prefill, Transaction, UtilityBill, UtilityBillRule
from api.services.gemini_services import parse_bill_with_gemini

logger = logging.getLogger(__name__)

DEFAULT_PREFILL_NAME = "Utility Bill"
DATE_WINDOW_DAYS = 45

PARSED_FIELDS = (
    "vendor",
    "account_number",
    "amount",
    "service_address",
    "bill_date",
    "due_date",
    "payment_date",
)


def _normalize_account_number(value: str) -> str:
    """Lowercase and strip non-alphanumerics so formatting differences (spaces,
    dashes) don't defeat the otherwise-exact account-number match."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _prefill_for_source(from_address: str) -> Optional[Prefill]:
    """The extraction prefill for an email: the prefill of any rule matching the
    sender, else the default 'Utility Bill' prefill."""
    rule = (
        UtilityBillRule.objects.filter(from_address=from_address)
        .select_related("prefill")
        .first()
    )
    if rule:
        return rule.prefill
    return Prefill.objects.filter(name=DEFAULT_PREFILL_NAME).first()


@db_transaction.atomic
def ingest_message(source_message_id: str, email: dict) -> Optional[UtilityBill]:
    """
    Creates a UtilityBill from a fetched email, parses it with Gemini, and
    resolves its account. Returns None if this message was already ingested
    successfully (dedupe on source_message_id). A previously FAILED record is
    re-attempted in place, so transient parse failures self-heal on re-poll.
    """
    existing = UtilityBill.objects.filter(
        source_message_id=source_message_id
    ).first()
    if existing and existing.status != UtilityBill.Status.FAILED:
        return None

    bill = existing or UtilityBill(source_message_id=source_message_id)
    bill.from_address = email.get("from_address", "")
    bill.subject = email.get("subject", "")
    bill.raw_text = email.get("text", "")
    bill.received_at = email.get("received_at")
    bill.status = UtilityBill.Status.PENDING
    bill.error_message = ""
    bill.save()

    prefill = _prefill_for_source(bill.from_address)
    if prefill is None:
        bill.status = UtilityBill.Status.FAILED
        bill.error_message = "No Utility Bill prefill configured."
        bill.save()
        return bill

    try:
        parsed = parse_bill_with_gemini(bill.raw_text, prefill)
    except Exception as exc:  # noqa: BLE001 - record any parse failure
        logger.exception("Failed to parse bill %s", source_message_id)
        bill.status = UtilityBill.Status.FAILED
        bill.error_message = str(exc)
        bill.save()
        return bill

    for field in PARSED_FIELDS:
        value = parsed.get(field)
        if value is not None:
            setattr(bill, field, value)
    bill.save()

    resolve_bill_account(bill)
    return bill


def resolve_bill_account(bill: UtilityBill) -> Optional[UtilityBillRule]:
    """
    Resolves a parsed bill to a ledger account via UtilityBillRule, keyed on the
    utility account number (fallback: address hint). Sets account/entity/rule
    and status (PARSED on success, UNRESOLVED otherwise).
    """
    rules = list(UtilityBillRule.objects.select_related("account", "entity"))
    match: Optional[UtilityBillRule] = None

    if bill.account_number:
        target = _normalize_account_number(bill.account_number)
        match = next(
            (r for r in rules if _normalize_account_number(r.account_number) == target),
            None,
        )

    if match is None and bill.service_address:
        haystack = bill.service_address.lower()
        match = next(
            (
                r
                for r in rules
                if r.address_hint and r.address_hint.lower() in haystack
            ),
            None,
        )

    if match:
        bill.rule = match
        bill.account = match.account
        bill.entity = match.entity
        bill.status = UtilityBill.Status.PARSED
    else:
        bill.rule = None
        bill.account = None
        bill.entity = None
        bill.status = UtilityBill.Status.UNRESOLVED
    bill.save()
    return match


def _bill_matches_transaction(bill: UtilityBill, txn: Transaction) -> bool:
    if bill.amount is None or abs(txn.amount) != bill.amount:
        return False
    rule = bill.rule
    needle = (rule.transaction_description_match or "").lower() if rule else ""
    if not needle or needle not in (txn.description or "").lower():
        return False
    # Anchor the date window on the actual payment date when available (it ~=
    # the bank transaction date), then the due date (payments cluster around
    # it), then the bill date.
    anchor_date = bill.payment_date or bill.due_date or bill.bill_date
    if anchor_date is not None:
        if abs((txn.date - anchor_date).days) > DATE_WINDOW_DAYS:
            return False
    return True


@db_transaction.atomic
def match_transactions_to_bills(transactions: Iterable[Transaction]) -> int:
    """
    Tags transactions whose amount + vendor + date uniquely match a parsed,
    unmatched bill. Sets suggested_account/entity/type on the transaction and
    links the bill (status MATCHED). Ambiguous candidates (>1 transaction per
    bill or >1 bill per transaction) are skipped for manual review.

    Returns the number of transactions tagged.
    """
    bills = list(
        UtilityBill.objects.filter(
            status=UtilityBill.Status.PARSED,
            matched_transaction__isnull=True,
            account__isnull=False,
        ).select_related("rule", "account", "entity")
    )
    txns = list(transactions)
    if not bills or not txns:
        return 0

    # Build candidate edges, then keep only 1:1 unique matches.
    edges = [
        (txn, bill)
        for txn in txns
        for bill in bills
        if _bill_matches_transaction(bill, txn)
    ]
    txn_degree: dict = defaultdict(int)
    bill_degree: dict = defaultdict(int)
    for txn, bill in edges:
        txn_degree[id(txn)] += 1
        bill_degree[bill.id] += 1

    txns_to_update: List[Transaction] = []
    bills_to_update: List[UtilityBill] = []
    for txn, bill in edges:
        if txn_degree[id(txn)] != 1 or bill_degree[bill.id] != 1:
            continue
        txn.suggested_account = bill.account
        txn.suggested_entity = bill.entity
        if bill.rule:
            txn.type = bill.rule.transaction_type
        bill.matched_transaction = txn
        bill.status = UtilityBill.Status.MATCHED
        txns_to_update.append(txn)
        bills_to_update.append(bill)

    if txns_to_update:
        Transaction.objects.bulk_update(
            txns_to_update, ["suggested_account", "suggested_entity", "type"]
        )
        UtilityBill.objects.bulk_update(
            bills_to_update, ["matched_transaction", "status"]
        )

    return len(txns_to_update)
