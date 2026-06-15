"""
Service layer for utility-bill rule CRUD on the Settings page.

All UtilityBillRule business logic and database writes go through these pure
service functions, which return dataclass result objects (per the service-layer
pattern). Mirrors account_services.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction as db_transaction
from django.db.models import ProtectedError, QuerySet

from api.models import Account, Entity, UtilityBillRule


@dataclass
class BillRuleResult:
    """Result of a utility-bill-rule create/update/delete operation."""
    success: bool
    rule: Optional[UtilityBillRule] = None
    error: Optional[str] = None


def get_bill_rules() -> List[UtilityBillRule]:
    """Returns all utility-bill rules, ordered by sender then subject."""
    return list(
        UtilityBillRule.objects.select_related("account").order_by(
            "from_address", "subject", "account_number"
        )
    )


def get_bill_rule_form_options() -> Tuple[QuerySet, QuerySet]:
    """Returns the (accounts, entities) querysets used to populate the rule
    edit form's dropdowns."""
    accounts = Account.objects.filter(is_closed=False).order_by("name")
    entities = Entity.objects.order_by("name")
    return accounts, entities


RULE_FIELDS = (
    "from_address",
    "subject",
    "account_number",
    "address_hint",
    "transaction_description_match",
    "account",
    "entity",
    "transaction_type",
)


@db_transaction.atomic
def save_bill_rule(
    cleaned_data: Dict[str, Any], instance: Optional[UtilityBillRule] = None
) -> BillRuleResult:
    """Creates or updates a utility-bill rule from validated form data.

    The caller (view) validates the form and passes ``form.cleaned_data``;
    ``instance`` is the rule being edited (None to create). Returns a
    BillRuleResult; on any DB error the transaction rolls back.
    """
    try:
        rule = instance or UtilityBillRule()
        for field in RULE_FIELDS:
            setattr(rule, field, cleaned_data.get(field))
        rule.save()
        return BillRuleResult(success=True, rule=rule)
    except Exception as e:  # pragma: no cover - defensive
        return BillRuleResult(success=False, error=str(e))


def delete_bill_rule(rule_id: int) -> BillRuleResult:
    """Deletes a utility-bill rule, gracefully blocking if still referenced.

    Ingested UtilityBill rows reference the rule with SET_NULL, so a delete is
    normally safe; the ProtectedError guard mirrors account deletion in case a
    future PROTECT relation is added.
    """
    try:
        rule = UtilityBillRule.objects.get(pk=rule_id)
    except UtilityBillRule.DoesNotExist:
        return BillRuleResult(success=False, error="Rule not found.")

    try:
        rule.delete()
        return BillRuleResult(success=True, rule=rule)
    except ProtectedError:
        return BillRuleResult(
            success=False,
            rule=rule,
            error="Can't delete this rule — it's still referenced by other records.",
        )
