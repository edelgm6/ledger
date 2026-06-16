"""
Service layer for loans: amortization-schedule CRUD plus the auto-matcher that
splits imported transactions into their principal/interest portions.

All Loan business logic and database writes go through these pure service
functions, which return dataclass result objects (per the service-layer
pattern). Mirrors bill_rule_services + bill_services.match_transactions_to_bills.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.db import transaction as db_transaction
from django.db.models import Max, QuerySet

from api.models import Account, Entity, Loan, LoanPayment, Transaction
from api.services import crud


@dataclass
class LoanResult:
    """Result of a loan create/update/delete operation."""

    success: bool
    loan: Optional[Loan] = None
    error: Optional[str] = None


def get_loans() -> List[Loan]:
    """Returns all loans, ordered by name, with their accounts preloaded."""
    return list(
        Loan.objects.select_related(
            "principal_account", "interest_account", "payment_account", "entity"
        ).order_by("name")
    )


def get_schedule(loan_id: int) -> List[LoanPayment]:
    """Returns a loan's schedule rows in order, with linked transactions."""
    return list(
        LoanPayment.objects.filter(loan_id=loan_id)
        .select_related("transaction")
        .order_by("sequence")
    )


def get_loan_form_options() -> Tuple[QuerySet, QuerySet, QuerySet, QuerySet]:
    """Returns the querysets used to populate the loan edit form's dropdowns:
    (liability accounts, expense accounts, all open accounts, entities)."""
    liability_accounts = Account.objects.filter(
        type=Account.Type.LIABILITY, is_closed=False
    ).order_by("name")
    expense_accounts = Account.objects.filter(
        type=Account.Type.EXPENSE, is_closed=False
    ).order_by("name")
    payment_accounts = Account.objects.filter(is_closed=False).order_by("name")
    entities = Entity.objects.order_by("name")
    return liability_accounts, expense_accounts, payment_accounts, entities


LOAN_FIELDS = (
    "name",
    "original_amount",
    "annual_interest_rate",
    "term_months",
    "start_date",
    "payment_amount",
    "principal_account",
    "interest_account",
    "payment_account",
    "description_match",
    "date_window_days",
    "entity",
)


def save_loan(
    cleaned_data: Dict[str, Any], instance: Optional[Loan] = None
) -> LoanResult:
    """Creates or updates a loan from validated form data and (re)generates its
    schedule. The caller (view) validates the form and passes ``form.cleaned_data``;
    ``instance`` is the loan being edited (None to create)."""
    loan, error = crud.save_model(
        Loan,
        LOAN_FIELDS,
        cleaned_data,
        instance,
        post_save=lambda loan: loan.generate_schedule(),
    )
    return LoanResult(success=error is None, loan=loan, error=error)


def delete_loan(loan_id: int) -> LoanResult:
    """Deletes a loan (and its unlinked schedule rows). Schedule rows that are
    linked to a transaction use SET_NULL, so the transactions survive."""
    loan, error = crud.delete_model(
        Loan,
        loan_id,
        not_found="Loan not found.",
        protected="Can't delete this loan — it's still referenced by other records.",
    )
    return LoanResult(success=error is None, loan=loan, error=error)


@db_transaction.atomic
def save_schedule_row(
    row_id: int,
    principal_amount: Decimal,
    interest_amount: Decimal,
    balance: Decimal,
) -> LoanResult:
    """Saves a schedule row as a balance anchor.

    Records the row's principal/interest split and pins the outstanding balance
    to ``balance`` as of this row, then re-amortizes everything forward from it.
    Every save creates a fresh anchor at that point: editing a payment means
    also declaring the resulting balance baseline. The anchor overrides any
    unreliable computed history before it and survives later re-amortizations.
    """
    try:
        row = LoanPayment.objects.select_related("loan").get(pk=row_id)
    except LoanPayment.DoesNotExist:
        return LoanResult(success=False, error="Schedule row not found.")

    loan = row.loan
    row.principal_amount = loan._round(principal_amount)
    row.interest_amount = loan._round(interest_amount)
    row.payment_amount = loan._round(row.principal_amount + row.interest_amount)
    row.balance_override = loan._round(balance)
    row.remaining_balance = row.balance_override
    row.save()
    loan.generate_schedule()
    return LoanResult(success=True, loan=loan)


@db_transaction.atomic
def clear_row_anchor(row_id: int) -> LoanResult:
    """Removes a row's balance anchor and re-amortizes the schedule from the
    computed history again."""
    try:
        row = LoanPayment.objects.select_related("loan").get(pk=row_id)
    except LoanPayment.DoesNotExist:
        return LoanResult(success=False, error="Schedule row not found.")

    loan = row.loan
    row.balance_override = None
    row.save()
    loan.generate_schedule()
    return LoanResult(success=True, loan=loan)


# --- Auto-matching -----------------------------------------------------------


def _candidate_loans(txn: Transaction, loans: List[Loan]) -> List[Loan]:
    """Loans an outflow transaction could belong to, by payment-account and/or
    description scoping (a loan with neither set matches any outflow)."""
    if txn.amount >= 0:  # loan payments are outflows (negative)
        return []
    description = (txn.description or "").lower()
    matches = []
    for loan in loans:
        if loan.payment_account_id and loan.payment_account_id != txn.account_id:
            continue
        if loan.description_match and loan.description_match.lower() not in description:
            continue
        matches.append(loan)
    return matches


def _match_scheduled_row(
    loan: Loan, txn: Transaction, amount: Decimal, taken_row_ids: set
) -> Optional[LoanPayment]:
    """The closest-dated unpaid scheduled row whose payment equals the amount and
    falls within the loan's date window (every fixed-rate row shares the same
    payment, so the date is the tie-breaker)."""
    rows = (
        loan.payments.filter(
            transaction__isnull=True,
            kind=LoanPayment.Kind.SCHEDULED,
            payment_amount=amount,
        )
        .exclude(id__in=taken_row_ids)
        .order_by("sequence")
    )
    best = None
    best_delta = None
    for row in rows:
        delta = abs((txn.date - row.date).days)
        if delta <= loan.date_window_days and (best_delta is None or delta < best_delta):
            best, best_delta = row, delta
    return best


def _record_off_schedule(
    loan: Loan, txn: Transaction, amount: Decimal
) -> Optional[LoanPayment]:
    """Records an off-schedule payment: principal-only (re-amortizing the rest)
    or, when it covers the remaining balance, a payoff that closes the loan."""
    balance = loan.remaining_balance()
    if balance <= 0:
        return None

    next_sequence = (
        loan.payments.aggregate(m=Max("sequence"))["m"] or 0
    ) + 1

    if amount >= balance:
        principal = balance
        interest = loan._round(amount - balance)  # any excess books as interest
        kind = LoanPayment.Kind.PAYOFF
        new_balance = Decimal("0.00")
    else:
        principal = amount
        interest = Decimal("0.00")
        kind = LoanPayment.Kind.PRINCIPAL_ONLY
        new_balance = loan._round(balance - principal)

    # Link the payment up front (both paths) so re-amortization counts it and
    # the caller doesn't have to re-link it.
    row = LoanPayment.objects.create(
        loan=loan,
        sequence=next_sequence,
        date=txn.date,
        payment_amount=amount,
        principal_amount=principal,
        interest_amount=interest,
        remaining_balance=new_balance,
        kind=kind,
        transaction=txn,
    )

    if kind == LoanPayment.Kind.PAYOFF:
        loan.is_closed = True
        loan.save(update_fields=["is_closed"])
    else:
        loan.generate_schedule()
    return row


@db_transaction.atomic
def match_transactions_to_loans(transactions: Iterable[Transaction]) -> int:
    """
    Tags imported transactions that belong to a loan. A scheduled-amount match
    links that schedule row; an off-schedule amount is recorded as a
    principal-only payment (re-amortizing the rest) or a payoff. Sets
    suggested_account/entity/type so the transaction surfaces in the table; the
    actual principal/interest split is filled in by get_loan_initial_data when
    the journal entry is opened. Transactions matching more than one loan are
    skipped for manual review.

    Returns the number of transactions tagged.
    """
    loans = list(
        Loan.objects.filter(is_closed=False).select_related(
            "principal_account", "interest_account", "payment_account", "entity"
        )
    )
    if not loans:
        return 0

    matched = 0
    taken_row_ids: set = set()
    for txn in transactions:
        candidates = _candidate_loans(txn, loans)
        if len(candidates) != 1:
            continue
        loan = candidates[0]
        amount = abs(txn.amount)

        row = _match_scheduled_row(loan, txn, amount, taken_row_ids)
        if row is not None:
            row.transaction = txn
            row.save()
        else:
            # _record_off_schedule creates and links the payment itself.
            row = _record_off_schedule(loan, txn, amount)
            if row is None:
                continue
        taken_row_ids.add(row.id)

        txn.suggested_account = loan.principal_account
        txn.suggested_entity = loan.entity
        txn.type = Transaction.TransactionType.PAYMENT
        txn.save()
        matched += 1

    return matched
