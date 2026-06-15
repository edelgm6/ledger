"""
Business logic for utility-bill ingestion, account resolution, and matching
ingested bills to uploaded bank transactions.

All DB writes for the bill feature live here (per the service-layer pattern).
"""
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, List, Optional

from django.db import transaction as db_transaction

from api.models import Transaction, UtilityBill, UtilityBillRule
from api.services.gemini_services import parse_bill_with_gemini
from api.services.gmail_services import (
    build_gmail_service,
    get_message_text,
    search_messages,
)

logger = logging.getLogger(__name__)

DATE_WINDOW_DAYS = 45


def _normalize_account_number(value: str) -> str:
    """Lowercase and strip non-alphanumerics so formatting differences (spaces,
    dashes) don't defeat the otherwise-exact account-number match."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


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

    return _parse_and_resolve_bill(bill)


def _parse_and_resolve_bill(bill: UtilityBill) -> UtilityBill:
    """Parses the bill's saved raw_text via Gemini, applies the extracted
    fields, and resolves its account. Records FAILED + error_message on a parse
    error. Assumes the raw email fields are already saved on `bill`; shared by
    ingest_message and retry_bill so re-parsing has one definition.
    """
    try:
        parsed = parse_bill_with_gemini(bill.raw_text)
    except Exception as exc:  # noqa: BLE001 - record any parse failure
        logger.exception("Failed to parse bill %s", bill.source_message_id)
        bill.status = UtilityBill.Status.FAILED
        bill.error_message = str(exc)
        bill.save()
        return bill

    # parse_bill_with_gemini returns only valid, coerced UtilityBill fields.
    for field, value in parsed.items():
        if value is not None:
            setattr(bill, field, value)
    bill.error_message = ""
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

    # Group candidate matches both ways so we can keep only unique 1:1 pairs.
    # Transactions are keyed by id() because they may be unsaved bulk_create
    # results without reliable pk/__eq__; bills always have a stable pk.
    txns_for_bill: dict = defaultdict(list)
    bills_for_txn: dict = defaultdict(list)
    for bill in bills:
        for txn in txns:
            if _bill_matches_transaction(bill, txn):
                txns_for_bill[bill.id].append(txn)
                bills_for_txn[id(txn)].append(bill)

    txns_to_update: List[Transaction] = []
    bills_to_update: List[UtilityBill] = []
    for bill in bills:
        candidates = txns_for_bill[bill.id]
        if len(candidates) != 1:
            continue
        txn = candidates[0]
        if len(bills_for_txn[id(txn)]) != 1:
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


@dataclass
class PollResult:
    """Counts from a single Gmail poll run."""
    fetched: int = 0
    new: int = 0
    parsed: int = 0
    unresolved: int = 0
    failed: int = 0


def poll_bill_emails() -> PollResult:
    """
    Searches Gmail for each configured (from_address, subject) pair and ingests
    any new messages. Idempotent via source_message_id dedupe. Shared by the
    scheduled management command and the Settings "Poll now" action.
    """
    result = PollResult()

    # Search each distinct (from_address, subject) once, even when several rules
    # share a vendor; account_number resolves the property afterward.
    search_keys = set(
        UtilityBillRule.objects.values_list("from_address", "subject")
    )
    if not search_keys:
        return result

    service = build_gmail_service()
    for from_address, subject in sorted(search_keys):
        for message_id in search_messages(service, from_address, subject):
            result.fetched += 1
            email = get_message_text(service, message_id)
            bill = ingest_message(message_id, email)
            if bill is None:
                continue  # already ingested
            result.new += 1
            if bill.status == UtilityBill.Status.PARSED:
                result.parsed += 1
            elif bill.status == UtilityBill.Status.UNRESOLVED:
                result.unresolved += 1
            elif bill.status == UtilityBill.Status.FAILED:
                result.failed += 1
    return result


def get_bills(limit: int = 200) -> List[UtilityBill]:
    """Returns the most recently ingested bills (newest first) for the monitor."""
    return list(
        UtilityBill.objects.select_related(
            "account", "matched_transaction"
        ).order_by("-created_at")[:limit]
    )


@db_transaction.atomic
def retry_bill(bill_id: int) -> Optional[UtilityBill]:
    """
    Re-parses a stored bill's saved raw_text via Gemini and re-resolves its
    account. Used by the Settings "Retry" action on FAILED bills (no Gmail
    round-trip — the email body is already stored).
    """
    try:
        bill = UtilityBill.objects.get(pk=bill_id)
    except UtilityBill.DoesNotExist:
        return None
    return _parse_and_resolve_bill(bill)
