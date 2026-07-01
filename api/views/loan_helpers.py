"""
Helper functions for rendering the Loans Settings section (loan CRUD plus the
amortization-schedule view).

These pure functions take data and return HTML strings via render_to_string.
They contain no database writes and no business logic. Mirrors
bill_settings_helpers.
"""

from typing import List, Optional

from django.db.models import QuerySet
from django.template.loader import render_to_string

from api.forms import LoanForm
from api.models import Loan, LoanPayment
from api.views.form_helpers import resolve_form_values


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
        "values": resolve_form_values(
            loan,
            form,
            text=(
                "name",
                "original_amount",
                "annual_interest_rate",
                "term_months",
                "payment_amount",
                "description_match",
                "date_window_days",
            ),
            dates=("start_date",),
            fks=(
                "principal_account",
                "interest_account",
                "payment_account",
                "entity",
            ),
            defaults={"date_window_days": "7"},
        ),
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
