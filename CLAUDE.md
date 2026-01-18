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

## Code Organization Patterns

This codebase follows a strict separation of concerns for maintainability and testability. The refactoring of `journal_entry_views.py` serves as the reference implementation of this pattern.

### Architecture Layers

```
Views (HTTP orchestration)
  ↓
Helpers (pure HTML rendering functions)
  ↓
Forms (field validation)
  ↓
Services (business logic + atomic DB writes)
  ↓
Models (domain entities)
```

### Service Layer Guidelines (`api/services/`)

Services contain all business logic and database writes:

- **All database writes must be in services** - No `.save()`, `.delete()`, or `.create()` in views
- **Use `@db_transaction.atomic`** for multi-step operations to ensure atomicity
- **Return dataclass result objects** (e.g., `SaveResult`, `ValidationResult`) with:
  - `success: bool` - Whether operation succeeded
  - `data: Optional[Model]` - The created/updated object
  - `error: Optional[str]` - Error message if failed
- **Use bulk operations** - `bulk_create()`, `bulk_update()` for efficiency
- **Type hints required** on all function parameters and return types
- **Pure functions** - No HTTP dependencies (no `request` objects)
- **Single responsibility** - Each function does one thing well

**Example:**
```python
@dataclass
class SaveResult:
    success: bool
    journal_entry: Optional[JournalEntry] = None
    error: Optional[str] = None

@db_transaction.atomic
def save_journal_entry(
    date: datetime.date,
    memo: str,
    items: List[Dict[str, Any]]
) -> SaveResult:
    """Creates a journal entry with balanced items."""
    # Validation
    if not validate_items_balance(items):
        return SaveResult(success=False, error="Debits must equal credits")

    # Create entry
    entry = JournalEntry.objects.create(date=date, memo=memo)

    # Bulk create items
    item_objects = [JournalEntryItem(**item, journal_entry=entry) for item in items]
    JournalEntryItem.objects.bulk_create(item_objects)

    return SaveResult(success=True, journal_entry=entry)
```

### Helper Function Guidelines (`api/views/*_helpers.py`)

Helpers are pure functions for HTML rendering:

- **Pure functions** - Given the same input, always return the same output
- **No database writes** - Only read data passed as parameters
- **No business logic** - No calculations, validations, or complex transformations
- **Accept data structures, return HTML strings** - Use `render_to_string()`
- **Template-focused** - Thin wrappers around Django templates
- **No HTTP dependencies** - No `request` objects

**Example:**
```python
def render_journal_entry_form(
    journal_entry: Optional[JournalEntry] = None,
    accounts: Optional[List[Account]] = None
) -> str:
    """Renders the journal entry form HTML."""
    form = JournalEntryForm(instance=journal_entry)
    return render_to_string(
        'journal_entry_form.html',
        {'form': form, 'accounts': accounts}
    )

def render_journal_entry_table(
    entries: List[JournalEntry],
    row_url: str
) -> str:
    """Renders the journal entry table HTML."""
    return render_to_string(
        'journal_entry_table.html',
        {'entries': entries, 'row_url': row_url}
    )
```

### View Guidelines (`api/views/`)

Views handle HTTP orchestration only:

- **HTTP orchestration** - Parse requests, call services, render responses
- **Call services for business logic** - Never implement business logic in views
- **Call helpers for rendering** - Never build HTML strings in views
- **No direct database writes** - All writes go through services
- **No complex calculations** - Delegate to services
- **Minimal logic** - Just routing between services and helpers

**Example:**
```python
def post(self, request, journal_entry_id=None):
    # 1. Parse action
    action = request.POST.get("action")

    # 2. Handle via service
    if action == "delete":
        result = delete_journal_entry(journal_entry_id)
    else:
        form = JournalEntryForm(request.POST)
        if form.is_valid():
            result = save_journal_entry(**form.cleaned_data)

    # 3. Handle result
    if not result.success:
        return HttpResponse(result.error, status=400)

    # 4. Render via helpers
    entries = get_journal_entries()  # Service function
    table_html = render_journal_entry_table(entries, self.row_url)
    form_html = render_journal_entry_form()

    return HttpResponse(table_html + form_html)
```

### Form Guidelines (`api/forms.py`)

Forms handle field-level validation only:

- **Field validation** - Type checking, format validation, range checks
- **No business logic** - No cross-model validations or complex rules
- **No database writes** - Forms validate, services save
- **Use custom fields** - Like `CommaDecimalField` for currency formatting

### Benefits of This Pattern

1. **Testability** - Services and helpers are pure functions, easy to unit test
2. **Reusability** - Services can be called from views, management commands, Celery tasks
3. **Maintainability** - Clear separation makes it easy to find and modify code
4. **Type Safety** - Type hints enable static analysis and IDE autocomplete
5. **Atomicity** - Database operations are properly wrapped in transactions

### Reference Implementation

See these files for the canonical example:
- `api/services/journal_entry_services.py` - Service layer
- `api/views/journal_entry_helpers.py` - Helper functions
- `api/views/journal_entry_views.py` - View layer
- `api/tests/services/test_journal_entry_services.py` - Service tests

### Anti-Patterns to Avoid

❌ **Database writes in views:**
```python
def post(self, request):
    transaction = form.save()  # NO!
    transaction.delete()  # NO!
```

❌ **Business logic in views:**
```python
def post(self, request):
    # Complex filtering and calculations
    transactions = Transaction.objects.filter(...)  # NO!
    total = sum(t.amount for t in transactions)  # NO!
```

❌ **HTML building in views:**
```python
def get(self, request):
    html = "<table>"  # NO!
    for item in items:
        html += f"<tr><td>{item}</td></tr>"
    return HttpResponse(html)
```

✅ **Correct pattern:**
```python
def post(self, request):
    # Service handles business logic
    result = transaction_service.save_transaction(**form.cleaned_data)

    # Helper handles rendering
    html = transaction_helpers.render_transaction_table(result.transactions)

    return HttpResponse(html)
```
