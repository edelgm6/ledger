---
name: finance-dashboard
description: Build or refresh an interactive, visual HTML dashboard of the user's finances (income statement, balance sheet, cash flow, KPIs, callouts, account drill-downs, month/quarter/year views) from the Ledger reporting API. Use when the user asks to create, update, or open a finance/accounting dashboard, or to visualize their ledger data. Read-only; writes a self-contained dashboards/dashboard.html.
---

# Finance dashboard

Fetch financial data, inject it into the prebuilt shell at `template.html` (in this skill's
directory), and write a self-contained `dashboards/dashboard.html`. All interactivity —
Month/Quarter/Year toggle, the three statements, KPI tiles, callouts, and account drill-downs
— is already built into the template and runs client-side over the embedded JSON.

**Do this with `fetch.py` (the fast path below), not by hand.** The script fetches, computes
callouts, assembles the blob, injects it, and writes the file in one shot — in ~15s. Fetching
piecemeal through MCP tools and re-transcribing the payloads by hand is the slow path and can
take many minutes; only fall back to it if the script genuinely can't run.

## Critical guardrails

- **Never commit the output.** `dashboards/dashboard.html` contains real financial figures;
  this repo is public. `dashboards/` is gitignored — keep it that way, and don't `git add` it.
  The skill files (`SKILL.md`, `template.html`, `fetch.py`) hold no data and are safe to commit.
- **Read-only.** Only GET the reporting endpoints (`/api/v1/reports/*` + the account/entity
  lists) — via `fetch.py` or the `mcp__ledger__*` tools. Never write to the DB or app.
- **Don't print the API key or the raw prod host** in your replies. `fetch.py` reads them from
  the environment / `mcp_server/.env` and never echoes them — keep it that way.

## Fast path — run the script

```bash
python3 .claude/skills/finance-dashboard/fetch.py            # trailing 12 full months
python3 .claude/skills/finance-dashboard/fetch.py --full     # drill EVERY open account (slower)
python3 .claude/skills/finance-dashboard/fetch.py --from 2025-01-01 --to 2025-12-31
python3 .claude/skills/finance-dashboard/fetch.py --top 20   # drill the 20 largest accounts (default 12)
```

It is stdlib-only (no install), reads `LEDGER_API_BASE_URL` / `LEDGER_API_KEY` from the env or
`mcp_server/.env`, and:

1. Picks the window (default: **trailing 12 full months** — `to_date` = last day of last full
   month, `from_date` = first day of the month 11 months earlier). Override with `--from/--to`.
2. Fetches `reports/trend/` (the backbone), then per-month `reports/cash-flow/` and
   `reports/spending-by-entity/`, plus `accounts/` and `entities/` — concurrently.
3. Drills `reports/account-detail/` for the largest accounts by default (`--top N`, `--full`
   for all). The template degrades gracefully — undrilled accounts just show an empty panel.
4. Computes 3–6 callouts, injects the blob into the `<script id="ledger-data">` placeholder,
   and writes `dashboards/dashboard.html`.

Then verify and report (Step 6). If the run fails because the tools/creds aren't reachable,
tell the user to register/point the server per `mcp_server/README.md`, or use the fallback.

## Fallback — MCP tools by hand (only if the script can't run)

Use this only when `fetch.py` can't reach the API (e.g. no `.env`, or an MCP-only environment
where the `mcp__ledger__*` tools work but the script's network/creds don't). It produces the
same blob, just slowly. Call the tools, assemble one JSON object with **exactly** these keys,
and inject it the same way the script does:

```
{
  "meta": { "built_at": <ISO timestamp>, "from_date": ..., "to_date": ..., "months": [...] },
  "trend": [ ...balances... ],                       # get_trend → .balances
  "cash_flow_by_month": { "YYYY-MM": {...}, ... },   # get_cash_flow per month
  "spending_by_month":  { "YYYY-MM": {...}, ... },   # spending_by_entity per month
  "accounts": [...], "entities": [...],              # list_accounts / list_entities
  "account_detail": { "<id>": { account, items:[{date,label,amount}] }, ... },  # account_detail per open account
  "callouts": [ {severity, title, detail}, ... ]     # severity: good|bad|warn|info|neutral
}
```

`get_trend` is large and the harness spills it to a `tool-results/*.txt` file — read that file
directly (jq) instead of through context. Do the injection with a tiny script (read
`template.html`, `json.dumps` the blob, regex-replace the single-line `{"meta":...}`
placeholder, write `dashboards/dashboard.html`) — never hand-edit the large JSON.

## Step 6 — Report

Tell the user the output path and offer to open it (`open dashboards/dashboard.html` on macOS).
Mention it needs an internet connection on open (Chart.js loads from CDN). Note how many
accounts were drilled (e.g. "top 12; re-run with `--full` for all"). Do **not** commit it.

## Notes on the data contract (so the blob lines up with the template)

- **Signs:** income and expense `amount`s are positive; the template computes
  `net_income = sum(income) − sum(expense)` and recomputes every ratio (`tax_rate`,
  `savings_rate`, balance-sheet `metrics`) itself from `trend` — so the dedicated
  income/balance-sheet endpoints aren't needed.
- **Trend rows** carry a month-end `date`; the template keys periods off `date[:7]`.
  Income-statement rows are `flow_type:"flow"` with `account_type` income/expense; balance-
  sheet rows are `flow_type:"stock"`; it ignores the asset/liability flow rows so nothing
  double-counts.
- **`spending_by_entity`** omits empty sections and pre-sorts descending — fine, the template
  re-aggregates and re-sorts across the selected months.
- **Trend row origin (important):** every `reports/trend/` row carries a `statement` field
  (`"income_statement"` / `"balance_sheet"` / `"cash_flow"`). Filter on it — `flowRows` takes
  `income_statement`, `stockRows` takes `balance_sheet`. Don't sum flow rows by
  `flow_type`/`account_type` alone: the cash-flow statement re-emits non-cash expenses (e.g.
  depreciation) as add-backs identical to the income-statement line, so you'd double-count.
  (`template.html` keeps a dedupe fallback for servers that predate the field.)
