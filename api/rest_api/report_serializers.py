"""
Serialization helpers for the read-only reporting endpoints.

The statement engine (``api/statement.py``) and ``statement_services`` return
plain Python objects (``Balance``, ``EntityBalance``) and dataclasses
(``StatementSummary``, ``EntityIncomeSummary``, ``CashFlowMetrics``,
``StatementDetailData``), not Django models. These functions flatten those
objects into JSON-able dicts for ``rest_framework.response.Response`` (its
JSON encoder renders ``Decimal``/``date`` natively).

Pure functions: object → dict. No database access, no business logic. The
shapes mirror the hierarchy that ``api/views/statement_helpers`` renders to
HTML, so the JSON reconciles with the on-screen statements.
"""

from typing import Any, Dict, List

from api.services.statement_services import (
    CashFlowMetrics,
    EntityIncomeSummary,
    StatementDetailData,
    StatementSummary,
)
from api.statement import Balance, EntityBalance


def serialize_balance(balance: Balance) -> Dict[str, Any]:
    """One account's balance line (works for real or synthetic accounts)."""
    account = balance.account
    return {
        "account": account.name,
        "account_type": account.type,
        "sub_type": account.sub_type,
        "amount": balance.amount,
        "flow_type": balance.type,
    }


def serialize_entity_balance(entity_balance: EntityBalance) -> Dict[str, Any]:
    """One entity's balance within a statement section."""
    return {
        "entity_id": entity_balance.entity_id,
        "entity": entity_balance.name,
        "amount": entity_balance.amount,
        "sub_type": entity_balance.sub_type,
    }


def serialize_statement_summary(summary: StatementSummary) -> Dict[str, Any]:
    """The by-account type → sub_type → balances hierarchy as nested dicts."""
    return {
        account_type: {
            "name": type_summary.name,
            "total": type_summary.total,
            "sub_types": [
                {
                    "name": sub.name,
                    "total": sub.total,
                    "balances": [serialize_balance(b) for b in sub.balances],
                }
                for sub in type_summary.sub_types
            ],
        }
        for account_type, type_summary in summary.account_types.items()
    }


def _serialize_entity_section(section) -> Dict[str, Any]:
    return {
        "name": section.name,
        "total": section.total,
        "balances": [serialize_entity_balance(b) for b in section.balances],
    }


def serialize_entity_income_summary(summary: EntityIncomeSummary) -> Dict[str, Any]:
    """Income/expense broken out by entity, largest sources/uses first."""
    return {
        "income_total": summary.income_total,
        "expense_total": summary.expense_total,
        "net_income": summary.net_income,
        "income_sub_types": [
            _serialize_entity_section(s) for s in summary.income_sub_types
        ],
        "expense_sub_types": [
            _serialize_entity_section(s) for s in summary.expense_sub_types
        ],
    }


def serialize_cash_flow_metrics(metrics: CashFlowMetrics) -> Dict[str, Any]:
    """Flat cash-flow totals plus the per-account flows in each section."""
    return {
        "cash_from_operations": metrics.cash_from_operations,
        "cash_from_financing": metrics.cash_from_financing,
        "cash_from_investing": metrics.cash_from_investing,
        "net_cash_flow": metrics.net_cash_flow,
        "levered_cash_flow": metrics.levered_cash_flow,
        "levered_cash_flow_post_restricted": (
            metrics.levered_cash_flow_post_restricted
        ),
        "cash_flow_discrepancy": metrics.cash_flow_discrepancy,
        "operations_flows": [serialize_balance(b) for b in metrics.operations_flows],
        "financing_flows": [serialize_balance(b) for b in metrics.financing_flows],
        "investing_flows": [serialize_balance(b) for b in metrics.investing_flows],
    }


def serialize_trend_balances(balances: List[Balance]) -> List[Dict[str, Any]]:
    """Monthly time-series rows; each balance carries its month-end date and the
    statement it came from ("income_statement" / "balance_sheet" / "cash_flow"),
    so a consumer can reconstruct one statement without double-counting rows the
    cash-flow statement re-emits (e.g. depreciation add-backs)."""
    return [
        {
            **serialize_balance(balance),
            "date": balance.date,
            "statement": getattr(balance, "statement", None),
        }
        for balance in balances
    ]


def serialize_detail(detail: StatementDetailData) -> Dict[str, Any]:
    """Signed line-item drill-down for an account or entity section."""
    return {
        "account": detail.account.name if detail.account else None,
        "items": [
            {
                "date": item.journal_entry.date,
                "label": item.display_label,
                "account": item.account.name,
                "entity": item.entity.name if item.entity else None,
                "amount": item.amount_signed,
                "type": item.type,
            }
            for item in detail.journal_entry_items
        ],
    }
