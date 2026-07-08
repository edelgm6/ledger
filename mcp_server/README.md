# Ledger MCP Server

A read-only [MCP](https://modelcontextprotocol.io) server that gives an agent
(Claude Cowork / Claude Code) native tools for querying your Ledger accounting
data — answering spending questions, building dashboards, and writing summaries.

It's a thin HTTP client over the Ledger reporting API (`/api/v1/reports/*`). It
**never touches the database** and only calls GET/reporting endpoints, so it is
read-only by construction and needs no database credentials — just the API base
URL and the shared API key.

## Tools

| Tool | What it returns |
| --- | --- |
| `get_income_statement(from_date, to_date, group_by)` | Revenue/expense/net income for a range; `group_by="entity"` for a payee breakdown |
| `get_balance_sheet(to_date)` | Assets/liabilities/equity + ratios at a point in time |
| `get_cash_flow(from_date, to_date)` | Operations / financing / investing cash flows |
| `spending_by_entity(from_date, to_date)` | Income & expense by entity, largest first |
| `get_trend(from_date, to_date)` | Month-by-month balances (time series for charts) |
| `account_detail(account_id, from_date, to_date)` | Signed line items for one account |
| `entity_detail(sub_type, entity_id, from_date, to_date)` | Signed line items for one entity section |
| `list_transactions(account, type, is_closed)` | Raw transactions |
| `list_accounts(type, is_closed)` | Chart of accounts (with ids) |
| `list_entities(is_closed)` | Entities/payees (with ids) |

Dates are `YYYY-MM-DD`. Omit them to default to the last full calendar month.

## Configuration

Two environment variables:

- `LEDGER_API_BASE_URL` — your deployed Ledger API root, e.g.
  `https://<your-app-host>/api/v1` (use `http://127.0.0.1:8000/api/v1` to point
  at a local dev server)
- `LEDGER_API_KEY` — the same value set as `LEDGER_API_KEY` on the server

### Register with Claude Code / Cowork

Add to your MCP config (e.g. `.mcp.json` or the Claude Code MCP settings):

```json
{
  "mcpServers": {
    "ledger": {
      "command": "uv",
      "args": [
        "run", "--with", "mcp[cli]", "--with", "httpx",
        "python", "mcp_server/server.py"
      ],
      "env": {
        "LEDGER_API_BASE_URL": "https://<your-app-host>/api/v1",
        "LEDGER_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## Example prompts

Once connected, ask Cowork things like:

- "What did I spend the most on last quarter? Build a dashboard."
- "Summarize last quarter's cash flow and flag anything unusual."
- "Chart my monthly expenses for 2025 and write a one-paragraph summary."
- "How did my net income trend month over month this year?"

Cowork calls these tools, then writes standalone artifacts (e.g.
`dashboard.html`, `summary.md`) from the returned JSON — no changes to the
Ledger app are needed.

## Local smoke test

```bash
# Point at a locally running dev server (uv run python manage.py runserver),
# with LEDGER_API_KEY set the same in both places.
LEDGER_API_BASE_URL=http://127.0.0.1:8000/api/v1 \
LEDGER_API_KEY=dev-key \
uv run --with 'mcp[cli]' --with httpx mcp dev mcp_server/server.py
```

`mcp dev` opens the MCP Inspector so you can invoke each tool by hand.
