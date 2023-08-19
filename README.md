# ledger

Ledger is a personal accounting tool to generate the three accounting statements (income statement, balance sheet, statement of cash flows).

## Retool frontend

Ledger is designed to be used with a Retool frontend which can be found in the `frontend` directory.

* Download `Ledger.json` from the `frontend` directory
* Create a Retool account at retool.com
* Create a new app via `From JSON/ZIP`
* Select Ledger.json
* Create a 'Resource' in Retool called `Ledger` that contains:
 * Base URL from where you hosted the backend (e.g., `https://your-site-000.fly.dev/`)
 * An Authorization header (e.g. Key == `Authorization`, value == `Token [Your Authorization Token]`) — you'll have to generate this token from the backend's admin site once it's hosted