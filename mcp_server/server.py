"""
Ledger MCP server — read-only agent access to production accounting data.

Exposes the Ledger reporting API (`/api/v1/reports/*` plus the raw list
endpoints) as typed MCP tools so Claude Cowork can answer spending questions,
build dashboards, and write summaries. It is a thin HTTP client over the
deployed Django API: it never touches the database directly, so it inherits the
API's read-only guarantee and needs no database credentials — only the base URL
and the shared API key.

Config (env vars):
  LEDGER_API_BASE_URL  e.g. https://fast-cliffs-86166.herokuapp.com/api/v1
  LEDGER_API_KEY       the same key the server checks (Authorization: Api-Key ...)

Run:  uv run --with 'mcp[cli]' --with httpx python mcp_server/server.py
"""

import os
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.environ.get("LEDGER_API_BASE_URL", "").rstrip("/")
API_KEY = os.environ.get("LEDGER_API_KEY", "")

mcp = FastMCP("ledger")

# One pooled client, reused across every tool call so an agent's many sequential
# requests share keep-alive connections instead of re-doing the TLS handshake.
_client = httpx.Client(
    headers={"Authorization": f"Api-Key {API_KEY}"}, timeout=30.0
)


def _get(path: str, params: Optional[dict] = None) -> Any:
    """GET a reporting endpoint and return parsed JSON (or an error dict)."""
    if not BASE_URL:
        return {"error": "LEDGER_API_BASE_URL is not set."}
    if not API_KEY:
        return {"error": "LEDGER_API_KEY is not set."}

    # Drop unset optional filters so the API applies its own defaults.
    clean = {k: v for k, v in (params or {}).items() if v is not None}
    try:
        response = _client.get(f"{BASE_URL}/{path.lstrip('/')}", params=clean)
    except httpx.HTTPError as exc:
        return {"error": f"Request failed: {exc}"}

    if response.status_code != 200:
        return {"error": f"HTTP {response.status_code}", "body": response.text[:500]}
    return response.json()


# --- Reporting tools (aggregations wrapping the statement engine) -----------


@mcp.tool()
def get_income_statement(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    group_by: str = "account",
) -> Any:
    """Income statement (revenue, expenses, net income) for a date range.

    Dates are YYYY-MM-DD; omit them to default to the last full month.
    group_by="entity" breaks income/expense out by payee/counterparty instead
    of by account.
    """
    return _get(
        "reports/income/",
        {"from_date": from_date, "to_date": to_date, "group_by": group_by},
    )


@mcp.tool()
def get_balance_sheet(to_date: Optional[str] = None) -> Any:
    """Point-in-time balance sheet (assets, liabilities, equity) plus ratios.

    to_date is YYYY-MM-DD; omit to default to the end of last month.
    """
    return _get("reports/balance-sheet/", {"to_date": to_date})


@mcp.tool()
def get_cash_flow(
    from_date: Optional[str] = None, to_date: Optional[str] = None
) -> Any:
    """Cash flow statement (operations / financing / investing) for a range."""
    return _get("reports/cash-flow/", {"from_date": from_date, "to_date": to_date})


@mcp.tool()
def spending_by_entity(
    from_date: Optional[str] = None, to_date: Optional[str] = None
) -> Any:
    """Income and expense broken out by entity (who you paid / got paid by),
    largest first — the 'what did I spend the most on' view."""
    return _get(
        "reports/spending-by-entity/",
        {"from_date": from_date, "to_date": to_date},
    )


@mcp.tool()
def get_trend(
    from_date: Optional[str] = None, to_date: Optional[str] = None
) -> Any:
    """Month-by-month balances across a range — the time series for dashboards.

    Returns one row per account per month, each tagged with its month-end date.
    """
    return _get("reports/trend/", {"from_date": from_date, "to_date": to_date})


@mcp.tool()
def account_detail(
    account_id: int,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Any:
    """Signed journal-entry line items for one account over a range (drill-down).

    Get account_id from list_accounts.
    """
    return _get(
        "reports/account-detail/",
        {"account_id": account_id, "from_date": from_date, "to_date": to_date},
    )


@mcp.tool()
def entity_detail(
    sub_type: str,
    entity_id: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Any:
    """Signed line items for one entity within a statement section (sub_type).

    Pass entity_id=None for the Unassigned bucket. sub_type is an account
    sub_type such as "operating", "salary", or "tax".
    """
    return _get(
        "reports/entity-detail/",
        {
            "sub_type": sub_type,
            "entity_id": entity_id,
            "from_date": from_date,
            "to_date": to_date,
        },
    )


# --- Raw listings (for lookups / joins) -------------------------------------


@mcp.tool()
def list_transactions(
    account: Optional[str] = None,
    type: Optional[str] = None,
    is_closed: Optional[bool] = None,
) -> Any:
    """List raw transactions. Optional filters: account name, type
    (income/purchase/payment/transfer), is_closed."""
    return _get(
        "transactions/",
        {"account": account, "type": type, "is_closed": is_closed},
    )


@mcp.tool()
def list_accounts(
    type: Optional[str] = None, is_closed: Optional[bool] = None
) -> Any:
    """List the chart of accounts (id, name, type, sub_type). Filter by type
    (asset/liability/income/expense/equity) or is_closed."""
    return _get("accounts/", {"type": type, "is_closed": is_closed})


@mcp.tool()
def list_entities(is_closed: Optional[bool] = None) -> Any:
    """List entities (payees/counterparties): id, name, is_closed."""
    return _get("entities/", {"is_closed": is_closed})


if __name__ == "__main__":
    mcp.run()
