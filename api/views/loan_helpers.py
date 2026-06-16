"""
Helper functions for rendering the Loans Settings section (loan CRUD plus the
amortization-schedule view).

These pure functions take data and return HTML strings via render_to_string.
They contain no database writes and no business logic. Mirrors
bill_settings_helpers.
"""

from typing import Any, Dict, List, Optional

from django.db.models import QuerySet
from django.template.loader import render_to_string

from api.forms import LoanForm
from api.models import Loan, LoanPayment


def render_loans_content(
    loans: List[Loan],
    loan_form_html: str,
    selected_id: Optional[int] = None,
) -> str:
    """Combines the header + table + form into the swappable Loans fragment."""
    return render_to_string(
        "api/content/loans-content.html",
        {
            "loans": loans,
            "total": len(loans),
            "selected_id": selected_id,
            "loan_form": loan_form_html,
        },
    )


def _loan_form_values(
    loan: Optional[Loan], form: Optional[LoanForm]
) -> Dict[str, Any]:
    """Resolves the field values to display: submitted data on a bound (invalid)
    form, else the loan being edited, else blank-create defaults."""
    if form is not None and form.is_bound:
        data = form.data
        return {
            "name": data.get("name", ""),
            "original_amount": data.get("original_amount", ""),
            "annual_interest_rate": data.get("annual_interest_rate", ""),
            "term_months": data.get("term_months", ""),
            "start_date": data.get("start_date", ""),
            "payment_amount": data.get("payment_amount", ""),
            "principal_account": data.get("principal_account", ""),
            "interest_account": data.get("interest_account", ""),
            "payment_account": data.get("payment_account", ""),
            "description_match": data.get("description_match", ""),
            "date_window_days": data.get("date_window_days", "7"),
            "entity": data.get("entity", ""),
        }
    if loan is not None:
        return {
            "name": loan.name,
            "original_amount": loan.original_amount,
            "annual_interest_rate": loan.annual_interest_rate,
            "term_months": loan.term_months,
            "start_date": loan.start_date.isoformat() if loan.start_date else "",
            "payment_amount": loan.payment_amount if loan.payment_amount else "",
            "principal_account": str(loan.principal_account_id or ""),
            "interest_account": str(loan.interest_account_id or ""),
            "payment_account": str(loan.payment_account_id or ""),
            "description_match": loan.description_match,
            "date_window_days": loan.date_window_days,
            "entity": str(loan.entity_id or ""),
        }
    return {
        "name": "",
        "original_amount": "",
        "annual_interest_rate": "",
        "term_months": "",
        "start_date": "",
        "payment_amount": "",
        "principal_account": "",
        "interest_account": "",
        "payment_account": "",
        "description_match": "",
        "date_window_days": "7",
        "entity": "",
    }


def render_loan_form(
    liability_accounts: QuerySet,
    expense_accounts: QuerySet,
    payment_accounts: QuerySet,
    entities: QuerySet,
    loan: Optional[Loan] = None,
    change: Optional[str] = None,
    error: Optional[str] = None,
    form: Optional[LoanForm] = None,
) -> str:
    """Renders the loan add/edit form HTML.

    Args:
        liability_accounts: queryset for the Principal account dropdown.
        expense_accounts: queryset for the Interest account dropdown.
        payment_accounts: queryset for the (optional) Payment account dropdown.
        entities: Entity queryset for the Entity dropdown.
        loan: Existing loan being edited (None for the create form).
        change: Type of change just performed ("create"/"update"/"delete").
        error: A friendly error message to display inline.
        form: A bound form carrying validation errors to redisplay.
    """
    context = {
        "loan": loan,
        "change": change,
        "error": error,
        "form": form,
        "values": _loan_form_values(loan, form),
        "liability_accounts": liability_accounts,
        "expense_accounts": expense_accounts,
        "payment_accounts": payment_accounts,
        "entities": entities,
    }
    return render_to_string("api/entry_forms/loan-form.html", context)


def render_loan_schedule(
    loan: Loan,
    rows: List[LoanPayment],
    message: Optional[str] = None,
) -> str:
    """Renders the amortization-schedule table for one loan, with editable
    principal/interest cells."""
    return render_to_string(
        "api/content/loan-schedule.html",
        {
            "loan": loan,
            "rows": rows,
            "remaining_balance": loan.remaining_balance(),
            "message": message,
        },
    )
