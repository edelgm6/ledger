"""
Helper functions for rendering the utility-bill Settings sections (Bill Rules
config CRUD and the Utility Bills monitor).

These pure functions take data and return HTML strings via render_to_string.
They contain no database writes and no business logic. Mirrors settings_helpers.
"""

from typing import Any, Dict, List, Optional

from django.db.models import QuerySet
from django.template.loader import render_to_string

from api.forms import UtilityBillRuleForm
from api.models import Transaction, UtilityBill, UtilityBillRule


def render_bill_rules_content(
    rules: List[UtilityBillRule],
    rule_form_html: str,
    selected_id: Optional[int] = None,
) -> str:
    """Combines the header + table + form into the swappable Bill Rules fragment."""
    return render_to_string(
        "api/content/bill-rules-content.html",
        {
            "rules": rules,
            "total": len(rules),
            "selected_id": selected_id,
            "rule_form": rule_form_html,
        },
    )


def _rule_form_values(
    rule: Optional[UtilityBillRule], form: Optional[UtilityBillRuleForm]
) -> Dict[str, Any]:
    """Resolves the field values to display: submitted data on a bound (invalid)
    form, else the rule being edited, else blank-create defaults."""
    if form is not None and form.is_bound:
        data = form.data
        return {
            "from_address": data.get("from_address", ""),
            "subject": data.get("subject", ""),
            "account_number": data.get("account_number", ""),
            "address_hint": data.get("address_hint", ""),
            "transaction_description_match": data.get(
                "transaction_description_match", ""
            ),
            "account": data.get("account", ""),
            "entity": data.get("entity", ""),
            "transaction_type": data.get(
                "transaction_type", Transaction.TransactionType.PURCHASE
            ),
        }
    if rule is not None:
        return {
            "from_address": rule.from_address,
            "subject": rule.subject,
            "account_number": rule.account_number,
            "address_hint": rule.address_hint,
            "transaction_description_match": rule.transaction_description_match,
            "account": str(rule.account_id or ""),
            "entity": str(rule.entity_id or ""),
            "transaction_type": rule.transaction_type,
        }
    return {
        "from_address": "",
        "subject": "",
        "account_number": "",
        "address_hint": "",
        "transaction_description_match": "",
        "account": "",
        "entity": "",
        "transaction_type": Transaction.TransactionType.PURCHASE,
    }


def render_bill_rule_form(
    accounts: QuerySet,
    entities: QuerySet,
    rule: Optional[UtilityBillRule] = None,
    change: Optional[str] = None,
    error: Optional[str] = None,
    form: Optional[UtilityBillRuleForm] = None,
) -> str:
    """Renders the bill-rule add/edit form HTML.

    Args:
        accounts: Account queryset for the Account dropdown.
        entities: Entity queryset for the Entity dropdown.
        rule: Existing rule being edited (None for the create form).
        change: Type of change just performed ("create"/"update"/"delete").
        error: A friendly error message to display inline.
        form: A bound form carrying validation errors to redisplay.
    """
    context = {
        "rule": rule,
        "change": change,
        "error": error,
        "form": form,
        "values": _rule_form_values(rule, form),
        "accounts": accounts,
        "entities": entities,
        "type_choices": Transaction.TransactionType.choices,
    }
    return render_to_string("api/entry_forms/bill-rule-form.html", context)


def render_bills_content(
    bills: List[UtilityBill], message: Optional[str] = None
) -> str:
    """Renders the read-only Utility Bills monitor fragment (status list +
    Poll-now/Retry actions)."""
    return render_to_string(
        "api/content/bills-content.html",
        {
            "bills": bills,
            "total": len(bills),
            "message": message,
            "failed_status": UtilityBill.Status.FAILED,
        },
    )
