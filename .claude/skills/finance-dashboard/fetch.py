#!/usr/bin/env python3
"""
Finance-dashboard fetcher — builds dashboards/dashboard.html in one shot.

Talks directly to the same read-only Ledger reporting API the `ledger` MCP
server wraps (`/api/v1/reports/*` + the account/entity lists), so no payload
ever round-trips through the agent's context. Read-only by construction: only
GETs the reporting endpoints, never writes. Reads LEDGER_API_BASE_URL /
LEDGER_API_KEY from the environment or mcp_server/.env and never prints them.

Usage:
    python3 fetch.py                      # trailing 12 full months, top accounts drilled
    python3 fetch.py --full               # drill EVERY open account (slower)
    python3 fetch.py --from 2025-01-01 --to 2025-12-31
    python3 fetch.py --top 20             # drill the 20 largest accounts (default 12)

Stdlib only — no pip install needed. Run with any python3.
"""
import argparse, calendar, datetime, json, os, re, sys, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SKILL_DIR, "..", "..", ".."))
TEMPLATE  = os.path.join(SKILL_DIR, "template.html")
OUT       = os.path.join(REPO_ROOT, "dashboards", "dashboard.html")
ENV_FILE  = os.path.join(REPO_ROOT, "mcp_server", ".env")


def load_env():
    base = os.environ.get("LEDGER_API_BASE_URL", "")
    key  = os.environ.get("LEDGER_API_KEY", "")
    if (not base or not key) and os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                if k.strip() == "LEDGER_API_BASE_URL" and not base:
                    base = v
                elif k.strip() == "LEDGER_API_KEY" and not key:
                    key = v
    if not base or not key:
        sys.exit("LEDGER_API_BASE_URL / LEDGER_API_KEY not set (env or "
                 "mcp_server/.env). See mcp_server/README.md.")
    return base.rstrip("/"), key


BASE, KEY = load_env()


def get(path, **params):
    """GET a reporting endpoint, return parsed JSON. Read-only."""
    clean = {k: v for k, v in params.items() if v is not None}
    url = f"{BASE}/{path.lstrip('/')}"
    if clean:
        url += "?" + urllib.parse.urlencode(clean)
    req = urllib.request.Request(url, headers={"Authorization": f"Api-Key {KEY}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def month_window(today):
    """Trailing 12 full months ending with last month. Returns (from, to, [keys])."""
    first_this = today.replace(day=1)
    last_full_end = first_this - datetime.timedelta(days=1)          # end of last month
    to_date = last_full_end
    start = (to_date.replace(day=1))
    for _ in range(11):                                              # step back 11 months
        start = (start - datetime.timedelta(days=1)).replace(day=1)
    keys, cur = [], start
    while cur <= to_date:
        keys.append(cur.strftime("%Y-%m"))
        nxt = (cur.replace(day=28) + datetime.timedelta(days=7)).replace(day=1)
        cur = nxt
    return start.isoformat(), to_date.isoformat(), keys


def month_bounds(key):
    y, m = map(int, key.split("-"))
    return f"{key}-01", f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def usd(n):
    return ("-" if n < 0 else "") + "$" + f"{abs(n):,.0f}"


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def build_callouts(trend, spending, months):
    out = []
    first, last = months[0], months[-1]
    # net worth from balance-sheet (stock) rows — only the window endpoints, which
    # is all the net-worth callout reads.
    a = {first: 0.0, last: 0.0}; l = {first: 0.0, last: 0.0}
    for r in trend:
        if r.get("flow_type") != "stock":
            continue
        mk = r["date"][:7]
        if mk not in a:
            continue
        if r["account_type"] == "asset":
            a[mk] += num(r["amount"])
        elif r["account_type"] == "liability":
            l[mk] += num(r["amount"])
    nw = {mk: a[mk] - l[mk] for mk in (first, last)}
    net = {mk: num(spending[mk]["net_income"]) for mk in months if mk in spending}
    inc = {mk: num(spending[mk]["income_total"]) for mk in months if mk in spending}
    tot = sum(net.values())

    out.append({"severity": "good" if nw[last] >= nw[first] else "bad",
                "title": f"Net worth {usd(nw[last])}",
                "detail": f"{'Up' if nw[last]>=nw[first] else 'Down'} "
                          f"{usd(abs(nw[last]-nw[first]))} over the window "
                          f"(from {usd(nw[first])} at {first})."})
    if len(months) >= 2 and last in net:
        prev = months[-2]
        out.append({"severity": "bad" if net[last] < 0 else "good",
                    "title": f"{last} net income {usd(net[last])}",
                    "detail": f"Versus {usd(net.get(prev,0))} the month before "
                              f"on {usd(inc.get(last,0))} of income."})
    out.append({"severity": "info", "title": f"Trailing net income {usd(tot)}",
                "detail": f"Total across {first}–{last}. Monthly swings are "
                          f"dominated by unrealized investment gains/losses."})
    # biggest MoM swing in net income
    swing = max(((abs(net[months[i]]-net[months[i-1]]), months[i])
                 for i in range(1, len(months)) if months[i] in net), default=(0, None))
    if swing[1]:
        mk = swing[1]
        out.append({"severity": "warn",
                    "title": f"Biggest month-over-month swing: {mk}",
                    "detail": f"Net income moved {usd(swing[0])} vs. the prior month."})
    # top expense category (latest month) + top payees (window)
    cat = {}
    for r in trend:
        if r.get("flow_type") == "flow" and r["account_type"] == "expense" \
                and r["date"][:7] == last:
            cat[r["account"]] = cat.get(r["account"], 0) + num(r["amount"])
    payee = {}
    for mk in months:
        for grp in spending.get(mk, {}).get("expense_sub_types", []):
            for b in grp.get("balances", []):
                payee[b["entity"]] = payee.get(b["entity"], 0) + num(b["amount"])
    top_cat = sorted(cat.items(), key=lambda x: -x[1])[:1]
    top_pay = sorted(payee.items(), key=lambda x: -x[1])[:3]
    if top_cat:
        out.append({"severity": "neutral",
                    "title": f"Top spend category in {last}: {top_cat[0][0]}",
                    "detail": f"{usd(top_cat[0][1])}. Largest payees over the window: "
                              + ", ".join(f"{n} ({usd(v)})" for n, v in top_pay) + "."})
    # largest debt move over the window
    debt = {}
    for r in trend:
        if r.get("flow_type") == "stock" and r["account_type"] == "liability":
            debt.setdefault(r["account"], {})[r["date"][:7]] = num(r["amount"])
    moves = []
    for name, series in debt.items():
        f = series.get(first); L = series.get(last)
        if f is not None and L is not None:
            moves.append((L - f, name))
    if moves:
        d, name = max(moves, key=lambda x: abs(x[0]))
        out.append({"severity": "warn" if d > 0 else "good",
                    "title": f"Debt: {name} {'up' if d>0 else 'down'} {usd(abs(d))}",
                    "detail": f"Largest liability change over {first}–{last}."})
    return out[:6]


def rank_accounts(trend, open_accts, months):
    """Rank open accounts by magnitude for the default (partial) drill-down."""
    last = months[-1]
    mag = {}
    for r in trend:
        name = r["account"]
        if r.get("flow_type") == "stock" and r["date"][:7] == last:
            mag[name] = max(mag.get(name, 0), abs(num(r["amount"])))
        elif r.get("flow_type") == "flow":
            mag[name] = mag.get(name, 0) + abs(num(r["amount"]))
    return sorted(open_accts, key=lambda ac: -mag.get(ac["name"], 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm"); ap.add_argument("--to", dest="to")
    ap.add_argument("--full", action="store_true", help="drill every open account")
    ap.add_argument("--top", type=int, default=12, help="how many accounts to drill (default 12)")
    args = ap.parse_args()

    today = datetime.date.today()
    if args.frm and args.to:
        frm, to = args.frm, args.to
        months, cur = [], datetime.date.fromisoformat(frm).replace(day=1)
        end = datetime.date.fromisoformat(to)
        while cur <= end:
            months.append(cur.strftime("%Y-%m"))
            cur = (cur.replace(day=28) + datetime.timedelta(days=7)).replace(day=1)
    else:
        frm, to, months = month_window(today)

    print(f"window {frm} → {to} ({len(months)} months)", file=sys.stderr)

    # Each trend row carries a `statement` origin; the template filters on it so
    # cash-flow add-backs (e.g. depreciation) aren't summed into the income statement.
    trend    = get("reports/trend/", from_date=frm, to_date=to).get("balances", [])
    accounts = get("accounts/").get("accounts", [])
    entities = get("entities/").get("entities", [])
    print(f"trend rows {len(trend)} | accounts {len(accounts)} | entities {len(entities)}",
          file=sys.stderr)

    cash_flow_by_month, spending_by_month = {}, {}

    def fetch_month(mk):
        f, t = month_bounds(mk)
        return mk, get("reports/cash-flow/", from_date=f, to_date=t), \
                   get("reports/spending-by-entity/", from_date=f, to_date=t)

    open_accts = [a for a in accounts if not a.get("is_closed")]
    drill = open_accts if args.full else rank_accounts(trend, open_accts, months)[:args.top]

    def fetch_detail(ac):
        return str(ac["id"]), get("reports/account-detail/", account_id=ac["id"],
                                  from_date=frm, to_date=to)

    with ThreadPoolExecutor(max_workers=8) as ex:
        for mk, cf, sp in ex.map(fetch_month, months):
            cash_flow_by_month[mk] = cf
            spending_by_month[mk] = sp
        account_detail = {}
        for aid, det in ex.map(fetch_detail, drill):
            if det.get("account") and det.get("items"):
                account_detail[aid] = det
    print(f"cash_flow {len(cash_flow_by_month)} | spending {len(spending_by_month)} | "
          f"drilled {len(account_detail)}/{len(open_accts)} open accounts", file=sys.stderr)

    blob = {
        "meta": {"built_at": datetime.datetime.now().isoformat(timespec="seconds"),
                 "from_date": frm, "to_date": to, "months": months},
        "trend": trend,
        "cash_flow_by_month": cash_flow_by_month,
        "spending_by_month": spending_by_month,
        "accounts": accounts, "entities": entities,
        "account_detail": account_detail,
        "callouts": build_callouts(trend, spending_by_month, months),
    }

    with open(TEMPLATE) as f:
        html = f.read()
    new = re.sub(r'^\{"meta":.*\}\s*$', lambda _: json.dumps(blob, ensure_ascii=False),
                 html, count=1, flags=re.M)
    if new == html:
        sys.exit("ERROR: ledger-data placeholder not found in template.html")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(new)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
