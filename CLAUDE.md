# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git

Never run `git commit` or `git push` under any circumstances unless the user explicitly instructs you to in that message.

## Commands

```bash
# Run development server
uv run python manage.py runserver

# Run all tests
uv run python manage.py test

# Run specific test module
uv run python manage.py test api.tests.models.test_transaction
uv run python manage.py test api.tests.statement.test_balance_sheet

# Run with coverage
uv run coverage run --source='.' manage.py test
uv run coverage report

# Run Celery worker (for async Textract processing)
uv run celery -A api worker --loglevel=info

# Create migrations after model changes
uv run python manage.py makemigrations
uv run python manage.py migrate
```

## Architecture

Ledger is a Django personal accounting application that generates three accounting statements (income statement, balance sheet, statement of cash flows) using double-entry bookkeeping.

### Core Structure

- **ledger/** - Django project configuration (settings, urls, wsgi)
- **api/** - Main Django app containing all business logic
  - `models.py` - model classes for accounting entities
  - `statement.py` - Statement generation (IncomeStatement, BalanceSheet, CashFlowStatement, Trend)
  - `views/` - HTMX-based views returning HTML fragments
  - `services/` - Business logic (journal_entry_services.py)
  - `forms.py` - Django forms with custom CommaDecimalField for currency
  - `aws_services.py` - S3 uploads and Textract OCR integration
  - `tasks.py` - Celery tasks for async document processing

### Key Models and Relationships

**Account** → has many **Transactions** → each creates a **JournalEntry** → with multiple **JournalEntryItems** (debits/credits)

- **Entity**: Business entities (companies, individuals) which can be linked to accounts as a default (e.g., every time my Checking Account has a Transaction, auto-link to Ally Bank)
- **Account**: Chart of accounts with types (ASSET, LIABILITY, INCOME, EXPENSE, EQUITY) and sub_types
- **Transaction**: Financial transactions that auto-generate journal entries
- **TaxCharge**: Tax liability linked to transactions
- **Amortization**: Expense amortization over periods
- **Reconciliation**: Account balance verification with plug transactions

### Double-Entry Bookkeeping Logic

Every Transaction creates a JournalEntry with balanced JournalEntryItems:
- Debits increase: ASSET, EXPENSE accounts
- Debits decrease: LIABILITY, INCOME, EQUITY accounts
- `Account.get_balance(end_date, start_date)` sums JournalEntryItems respecting debit/credit rules

### Frontend Pattern

HTMX-based - views return HTML fragments via `render_to_string()`. No separate API endpoints; views render templates directly for AJAX updates.

### AI Integration

Gemini (Google) powers document parsing and an agentic recharacterization flow:
- `api/services/gemini_services.py` — paystub/bill parsing from PDFs/email
- `api/services/recharacterize_services.py` — multi-turn LLM bulk recharacterization of journal entry items

Runs async via Celery (e.g. `process_gemini_paystub` in `tasks.py`).

### Local Development Setup

Create `ledger/local_settings.py` with SECRET_KEY, AWS credentials, and database config (see README.md for template).

### Testing

Tests use Factory Boy (`api/tests/testing_factories.py`) for test data. Test structure:
- `api/tests/models/` - Model unit tests
- `api/tests/statement/` - Statement generation tests

## Code Organization

Strict layering for maintainability and testability: Views → Helpers → Forms → Services → Models.

- **Views** (`api/views/`): HTTP orchestration only — parse request, call a service, render via a helper. No model writes, no inline HTML, no business logic.
- **Helpers** (`api/views/*_helpers.py`): pure functions that render templates via `render_to_string()`. No DB access, no business logic.
- **Forms** (`api/forms.py`): field-level validation (e.g. `CommaDecimalField` for currency).
- **Services** (`api/services/`): business logic and DB writes. Wrap multi-step writes in `@db_transaction.atomic`, use bulk ops (`bulk_create`/`bulk_update`), type-hint everything, and return result dataclasses (`success` / `data` / `error`). Most writes live here, though a few forms still write directly — prefer services for new code.

Canonical example to follow: `api/services/journal_entry_services.py`, `api/views/journal_entry_views.py`, `api/views/journal_entry_helpers.py`, and `api/tests/services/test_journal_entry_services.py`.
