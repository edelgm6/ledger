# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run development server
python manage.py runserver

# Run all tests
python manage.py test

# Run specific test module
python manage.py test api.tests.models.test_transaction
python manage.py test api.tests.statement.test_balance_sheet

# Run with coverage
coverage run --source='.' manage.py test
coverage report

# Run Celery worker (for async Textract processing)
celery -A api worker --loglevel=info

# Create migrations after model changes
python manage.py makemigrations
python manage.py migrate
```

## Architecture

Ledger is a Django personal accounting application that generates three accounting statements (income statement, balance sheet, statement of cash flows) using double-entry bookkeeping.

### Core Structure

- **ledger/** - Django project configuration (settings, urls, wsgi)
- **api/** - Main Django app containing all business logic
  - `models.py` - 19 model classes for accounting entities
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

### Local Development Setup

Create `ledger/local_settings.py` with SECRET_KEY, AWS credentials, and database config (see README.md for template).

### Testing

Tests use Factory Boy (`api/tests/testing_factories.py`) for test data. Test structure:
- `api/tests/models/` - Model unit tests
- `api/tests/statement/` - Statement generation tests
