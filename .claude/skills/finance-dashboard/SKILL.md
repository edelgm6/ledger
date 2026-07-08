---
name: finance-dashboard
description: Build or refresh an interactive, visual HTML dashboard of the user's finances (income statement, balance sheet, cash flow, KPIs, callouts, account drill-downs, month/quarter/year views) from the Ledger MCP server. Use when the user asks to create, update, or open a finance/accounting dashboard, or to visualize their ledger data. Reads only via the read-only `ledger` MCP tools; writes a self-contained dashboards/dashboard.html.
---

# Finance dashboard

Fetch financial data through the read-only **`ledger` MCP server**, inject it into the
prebuilt shell at `template.html` (in this skill's directory), and write a self-contained
`dashboards/dashboard.html`. All interactivity — Month/Quarter/Year toggle, the three
statements, KPI tiles, callouts, and account drill-downs — is already built into the
template and runs client-side over the embedded JSON. Your job is just: **fetch → assemble
one JSON blob → inject → write.**

## Critical guardrails

- **Never commit the output.** `dashboards/dashboard.html` contains real financial figures;
  this repo is public. `dashboards/` is gitignored — keep it that way, and don't `git add`
  it. The skill files (`SKILL.md`, `template.html`) hold no data and are safe to commit.
- **Read-only.** Only call the `mcp__ledger__*` GET tools. Never write to the DB or app.
- **Don't print the API key** or the raw prod host in your replies.

## Step 1 — Preflight

Confirm the `ledger` MCP tools are available (`mcp__ledger__get_trend`, etc.). If they are
not registered, stop and tell the user to register the server per `mcp_server/README.md`
(set `LEDGER_API_BASE_URL` + `LEDGER_API_KEY`), then re-run.

## Step 2 — Choose the window

Default: **trailing 12 full months.** With today = the run date, `to_date` = the last day
of last full month; `from_date` = the first day of the month 11 months before that. Build
the list of month keys `months = ["YYYY-MM", ...]` (12 entries, chronological). Honor an
explicit override if the user names a range or a different length.

## Step 3 — Fetch (map tool output straight into the blob)

Dates are `YYYY-MM-DD`. Money fields come back as 2-dp **strings**; keep them as-is (the
template parses them). Make these calls:

1. `get_trend(from_date, to_date)` — **the backbone.** One flat `balances` array of
   `{account, account_type, sub_type, amount, flow_type, date}`. The template rebuilds the
   income statement, balance sheet, all KPIs, and every rate/ratio from this for any
   selected period, so this single call powers most of the dashboard. Put its `balances`
   array at `trend`.
2. For **each month** `m` in `months`, with that month's first/last day:
   - `get_cash_flow(from, to)` → store the full response at `cash_flow_by_month[m]`
     (cash flow can't be rebuilt from trend — it needs the operations/financing/investing
     split).
   - `spending_by_entity(from, to)` → store at `spending_by_month[m]` (entity breakdown
     isn't in trend).
   These 24 calls make the Cash Flow and Spending-by-Entity tabs dynamic per period.
3. `list_accounts()` → `accounts` (gives the id↔name map the drill-down needs).
   `list_entities()` → `entities`.
4. `account_detail(account_id, from_date, to_date)` for each **open** account (from
   `list_accounts`, `is_closed=false`) over the full window → store items at
   `account_detail["<id>"]`. This is the slow step (~one call per account). If the user
   asked for a fast build, fetch detail only for the largest accounts and note that the
   rest will populate on a fuller re-run (the template degrades gracefully — accounts
   without detail just show an empty drill-down).

Run independent calls in parallel where the tooling allows.

## Step 4 — Callouts

From the fetched data, compute a short, curated list (aim for 3–6) of the most useful
observations for the latest period and the window. Good candidates: largest expense
category and its biggest payee; biggest month-over-month swing in net income or spending;
savings-rate or tax-rate shift; any month that looks anomalous vs. its neighbors; notable
change in total assets or debt. Each is `{severity, title, detail}` where `severity` is one
of `good | bad | warn | info | neutral` (drives the badge color). Put them at `callouts`.

## Step 5 — Assemble, inject, write

Assemble one JSON object with exactly these keys:

```
{
  "meta": { "built_at": <ISO timestamp>, "from_date": ..., "to_date": ..., "months": [...] },
  "trend": [ ...balances... ],
  "cash_flow_by_month": { "YYYY-MM": {...}, ... },
  "spending_by_month":  { "YYYY-MM": {...}, ... },
  "accounts": [...], "entities": [...],
  "account_detail": { "<id>": {...}, ... },
  "callouts": [ {severity, title, detail}, ... ]
}
```

Then:
1. Read `template.html` from this skill's directory.
2. Replace the entire contents of the `<script id="ledger-data" type="application/json">
   ... </script>` block with the assembled JSON (the placeholder is the single-line
   `{"meta":...}` object). Leave the rest of the file byte-for-byte unchanged.
3. Write the result to `dashboards/dashboard.html` (create `dashboards/` if missing).

Prefer doing the injection with a tiny script (read template, `json.dumps` the blob, string-
replace the placeholder line, write output) rather than hand-editing — it's reliable and
keeps the large JSON out of the transcript.

## Step 6 — Report

Tell the user the output path and offer to open it (`open dashboards/dashboard.html` on
macOS). Mention it needs an internet connection on open (Chart.js loads from CDN). Do **not**
commit it. To refresh later, just re-run this skill — it re-fetches and overwrites.

## Notes on the data contract (so the blob lines up with the template)

- **Signs:** income and expense `amount`s are positive; the template computes
  `net_income = sum(income) − sum(expense)`. Ratios (`tax_rate`, `savings_rate`, balance-
  sheet `metrics`) are floats or `null` — but the template recomputes these itself from
  trend, so you don't need the dedicated income/balance-sheet endpoints.
- **Trend rows** carry a month-end `date`; the template keys periods off `date[:7]`.
  Income-statement rows are `flow_type:"flow"` with `account_type` income/expense; balance-
  sheet rows are `flow_type:"stock"`; it ignores the asset/liability flow rows so nothing
  double-counts.
- **`spending_by_entity`** omits empty sections and pre-sorts descending — fine, the
  template re-aggregates and re-sorts across the selected months.
