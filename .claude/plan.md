# Refactoring Plan: Clean Up Journal Entry Views & Services

## Current State Analysis

### journal_entry_views.py Issues
- **JournalEntryView.post()**: 120 lines of dense logic mixing HTTP, validation, and database operations
- Database writes scattered throughout the view (bulk_create, bulk_update, transaction.close(), paystub.save())
- Business logic split between views, forms, and mixins
- Difficult to test - requires full HTTP request/response cycle

### Current Structure
```
View.post() (120 lines):
├── Build formsets with choices
├── Validate forms (individual + combined)
├── Save formsets (returns unsaved instances)
├── Classify items as new vs changed
├── Bulk update changed items
├── Bulk create new items
├── Close transaction
├── Link paystub
├── Rebuild filter form
├── Get next transaction
├── Extract created entities
├── Rebuild entry form HTML
├── Rebuild table HTML
└── Return response
```

### What Works Well
✅ Forms handle field validation and entity creation
✅ Existing `journal_entry_services.py` has clean read-only functions
✅ HTMX pattern keeps responses as HTML fragments
✅ Query optimization with select_related()

## Refactoring Goals

### Target Architecture
```
┌─────────────────┐
│  View (HTTP)    │ ← Request/Response, Orchestration only
├─────────────────┤
│  Helpers        │ ← Pure functions for HTML rendering
├─────────────────┤
│  Forms          │ ← Field validation (keep as-is)
├─────────────────┤
│  Services       │ ← ALL business logic & database writes
├─────────────────┤
│  Models         │ ← Domain entities
└─────────────────┘
```

### Principles
1. **Views**: HTTP + orchestration only (build forms, call helpers/services, return responses)
2. **Helpers**: Stateless pure functions for HTML rendering (replacing mixins)
3. **Forms**: Field-level validation (already clean)
4. **Services**: All business logic, validation, and database writes
5. **Atomic operations**: Wrap service writes in transactions
6. **Testability**: Services and helpers can be unit tested without HTTP mocking
7. **No mixins**: Explicit imports over inheritance magic

## Implementation Plan

### Phase 1: Extend Service Layer

**File**: `api/services/journal_entry_services.py`

Add new service functions following existing patterns:

#### 1.1 Validation Service
```python
from dataclasses import dataclass
from typing import List
from decimal import Decimal

@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str]

def validate_journal_entry_balance(
    transaction: Transaction,
    debits_data: List[dict],
    credits_data: List[dict]
) -> ValidationResult:
    """
    Validates journal entry business rules:
    - Debits total equals credits total
    - Exactly one item matches transaction account/amount

    Returns ValidationResult with errors if invalid.
    """
    errors = []

    # Calculate totals
    debit_total = sum(item['amount'] for item in debits_data if item.get('amount'))
    credit_total = sum(item['amount'] for item in credits_data if item.get('amount'))

    # Check balance
    if debit_total != credit_total:
        errors.append(f"Debits (${debit_total}) and Credits (${credit_total}) must balance.")

    # Check transaction match
    formset_data = debits_data if transaction.amount >= 0 else credits_data
    matching_items = [
        item for item in formset_data
        if item.get('amount') == abs(transaction.amount)
        and item.get('account') == transaction.account
    ]

    if len(matching_items) != 1:
        errors.append("Must be one journal entry item with the Transaction's account and amount.")

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)
```

#### 1.2 Save Service
```python
from django.db import transaction as db_transaction

@dataclass
class SaveResult:
    success: bool
    journal_entry: Optional[JournalEntry]
    error: Optional[str] = None

@db_transaction.atomic
def save_journal_entry(
    transaction_obj: Transaction,
    debits_data: List[dict],
    credits_data: List[dict],
    paystub_id: Optional[int] = None
) -> SaveResult:
    """
    Saves journal entry with all items atomically.

    Steps:
    1. Create JournalEntry if doesn't exist
    2. Classify items as new vs existing
    3. Bulk update existing items
    4. Bulk create new items
    5. Close transaction
    6. Link paystub if provided

    All operations wrapped in atomic transaction.
    Returns SaveResult with journal_entry on success.
    """
    try:
        # 1. Get or create JournalEntry
        try:
            journal_entry = transaction_obj.journal_entry
        except JournalEntry.DoesNotExist:
            journal_entry = JournalEntry.objects.create(
                date=transaction_obj.date,
                transaction=transaction_obj
            )

        # 2. Process debits and credits
        new_items = []
        changed_items = []

        for item_data in debits_data:
            item = _create_journal_entry_item(
                journal_entry=journal_entry,
                item_data=item_data,
                entry_type=JournalEntryItem.JournalEntryType.DEBIT
            )
            if item:
                (changed_items if item.pk else new_items).append(item)

        for item_data in credits_data:
            item = _create_journal_entry_item(
                journal_entry=journal_entry,
                item_data=item_data,
                entry_type=JournalEntryItem.JournalEntryType.CREDIT
            )
            if item:
                (changed_items if item.pk else new_items).append(item)

        # 3. Bulk operations
        if changed_items:
            JournalEntryItem.objects.bulk_update(
                changed_items,
                ['amount', 'account', 'entity']
            )

        if new_items:
            JournalEntryItem.objects.bulk_create(new_items)

        # 4. Close transaction
        transaction_obj.close()

        # 5. Link paystub if provided
        if paystub_id:
            try:
                paystub = Paystub.objects.get(pk=paystub_id)
                paystub.journal_entry = journal_entry
                paystub.save()
            except (Paystub.DoesNotExist, ValueError):
                pass  # Paystub linking is optional

        return SaveResult(success=True, journal_entry=journal_entry)

    except Exception as e:
        # Transaction will rollback automatically
        return SaveResult(success=False, journal_entry=None, error=str(e))


def _create_journal_entry_item(
    journal_entry: JournalEntry,
    item_data: dict,
    entry_type: str
) -> Optional[JournalEntryItem]:
    """
    Helper to create JournalEntryItem from cleaned form data.
    Returns None if item has no amount (empty form).
    """
    amount = item_data.get('amount')
    if not amount:
        return None

    # Get existing item by ID, or create new one
    item_id = item_data.get('id')
    if item_id:
        item = JournalEntryItem.objects.get(pk=item_id)
    else:
        item = JournalEntryItem(journal_entry=journal_entry, type=entry_type)

    # Update fields
    item.amount = amount
    item.account = item_data.get('account')
    item.entity = item_data.get('entity')

    return item
```

#### 1.3 Helper Service
```python
@dataclass
class PostSaveContext:
    transactions: List[Transaction]
    highlighted_index: int
    highlighted_transaction: Optional[Transaction]
    created_entities: List[Entity]

def get_post_save_context(
    filter_form: TransactionFilterForm,
    current_index: int,
    debit_formset,
    credit_formset
) -> PostSaveContext:
    """
    Builds context for rendering after successful save.

    Handles:
    - Getting filtered transactions
    - Determining next transaction to highlight
    - Extracting entities created during form cleaning
    """
    if filter_form.is_valid():
        transactions = list(filter_form.get_transactions())
    else:
        # Fallback to default filter
        transactions = list(Transaction.objects.filter(
            is_closed=False,
            type__in=[
                Transaction.TransactionType.INCOME,
                Transaction.TransactionType.PURCHASE
            ]
        ))

    # Get next transaction (handle index out of bounds)
    if not transactions:
        return PostSaveContext(
            transactions=[],
            highlighted_index=0,
            highlighted_transaction=None,
            created_entities=[]
        )

    try:
        highlighted_transaction = transactions[current_index]
        highlighted_index = current_index
    except IndexError:
        highlighted_transaction = transactions[0]
        highlighted_index = 0

    # Extract created entities from formsets
    created_entities = []
    for formset in [debit_formset, credit_formset]:
        for form in formset:
            if hasattr(form, 'created_entity'):
                created_entities.append(form.created_entity)

    return PostSaveContext(
        transactions=transactions,
        highlighted_index=highlighted_index,
        highlighted_transaction=highlighted_transaction,
        created_entities=created_entities
    )
```

### Phase 2: Create Helper Functions (Replace Mixin)

**File**: `api/views/journal_entry_helpers.py` (NEW)

Extract HTML rendering logic from `JournalEntryViewMixin` into pure functions:

```python
from typing import List, Optional
from django.template.loader import render_to_string
from api.models import Transaction, Paystub, S3File, Entity
from api.services.journal_entry_services import (
    get_debits_and_credits,
    get_formsets,
    get_initial_data,
)
from api.forms import JournalEntryMetadataForm


def render_paystubs_table() -> str:
    """
    Renders the paystubs table HTML.

    Shows a poller if any Textract jobs are still processing,
    otherwise shows unlinked paystubs.
    """
    outstanding_textract_jobs = S3File.objects.filter(analysis_complete__isnull=True)
    if outstanding_textract_jobs:
        return render_to_string("api/tables/paystubs-table-poller.html")

    paystubs = (
        Paystub.objects.filter(journal_entry__isnull=True)
        .select_related("document")
        .order_by("title")
    )
    return render_to_string("api/tables/paystubs-table.html", {"paystubs": paystubs})


def render_journal_entry_form(
    transaction: Optional[Transaction],
    index: int = 0,
    paystub_id: Optional[int] = None,
    created_entities: Optional[List[Entity]] = None,
    debit_formset=None,
    credit_formset=None,
    form_errors: Optional[List[str]] = None,
) -> str:
    """
    Renders the journal entry form HTML.

    If formsets are not provided, builds them from transaction data.
    Can optionally prefill from paystub or show validation errors.
    """
    if not transaction:
        return ""

    # Build formsets if not provided
    if not (debit_formset and credit_formset):
        journal_entry_debits, journal_entry_credits = get_debits_and_credits(transaction)
        bound_debits_count = journal_entry_debits.count()
        bound_credits_count = journal_entry_credits.count()

        # Determine if transaction's source account is a debit
        is_debit = transaction.amount >= 0

        if bound_debits_count + bound_credits_count == 0:
            debits_initial_data, credits_initial_data = get_initial_data(
                transaction=transaction, paystub_id=paystub_id
            )
        else:
            debits_initial_data = []
            credits_initial_data = []

        debit_formset, credit_formset = get_formsets(
            debits_initial_data=debits_initial_data,
            credits_initial_data=credits_initial_data,
            journal_entry_debits=journal_entry_debits,
            journal_entry_credits=journal_entry_credits,
            bound_debits_count=bound_debits_count,
            bound_credits_count=bound_credits_count,
        )
    else:
        is_debit = True  # Default if formsets provided with errors

    # Build metadata form
    metadata = {"index": index, "paystub_id": paystub_id}
    metadata_form = JournalEntryMetadataForm(initial=metadata)

    # Calculate totals
    debit_prefilled_total = debit_formset.get_entry_total()
    credit_prefilled_total = credit_formset.get_entry_total()

    context = {
        "debit_formset": debit_formset,
        "credit_formset": credit_formset,
        "transaction_id": transaction.id,
        "autofocus_debit": is_debit,
        "form_errors": form_errors or [],
        "debit_prefilled_total": debit_prefilled_total,
        "credit_prefilled_total": credit_prefilled_total,
        "metadata_form": metadata_form,
        "created_entities": created_entities,
    }

    return render_to_string("api/entry_forms/journal-entry-item-form.html", context)


def extract_created_entities(formsets) -> List[Entity]:
    """
    Extracts entities that were created during form cleaning.

    Forms create entities on-the-fly if user enters a new entity name.
    This helper collects them to pass to the next form render.
    """
    created_entities = []
    for formset in formsets:
        for form in formset:
            if hasattr(form, 'created_entity'):
                created_entities.append(form.created_entity)
    return created_entities
```

### Phase 3: Simplify JournalEntryView.post()

**File**: `api/views/journal_entry_views.py`

Transform the 120-line post method into clean orchestration:

```python
from api.services.journal_entry_services import (
    get_accounts_choices,
    get_entities_choices,
    validate_journal_entry_balance,
    save_journal_entry,
    get_post_save_context,
)
from api.views.journal_entry_helpers import (
    render_journal_entry_form,
    render_paystubs_table,
    extract_created_entities,
)
from api.views.transaction_views import TransactionsViewMixin

class JournalEntryView(TransactionsViewMixin, LoginRequiredMixin, View):
    view_template = "api/views/journal-entry-view.html"

    def post(self, request, transaction_id):
        """
        Saves journal entry for a transaction.

        Flow:
        1. Build and validate forms
        2. Validate business rules via service
        3. Save via service (atomic)
        4. Build response context via service
        5. Render response via helpers
        """
        # 1. Build forms
        transaction = get_object_or_404(Transaction, pk=transaction_id)

        JournalEntryItemFormset = modelformset_factory(
            JournalEntryItem,
            formset=BaseJournalEntryItemFormset,
            form=JournalEntryItemForm,
        )

        accounts_choices = get_accounts_choices()
        entities_choices = get_entities_choices()

        debit_formset = JournalEntryItemFormset(
            request.POST,
            prefix="debits",
            form_kwargs={
                "open_accounts_choices": accounts_choices,
                "open_entities_choices": entities_choices,
            },
        )
        credit_formset = JournalEntryItemFormset(
            request.POST,
            prefix="credits",
            form_kwargs={
                "open_accounts_choices": accounts_choices,
                "open_entities_choices": entities_choices,
            },
        )
        metadata_form = JournalEntryMetadataForm(request.POST)

        # 2. Validate forms (field-level)
        if not (debit_formset.is_valid() and credit_formset.is_valid() and metadata_form.is_valid()):
            # Render form with field errors
            entry_form_html = render_journal_entry_form(
                transaction=transaction,
                debit_formset=debit_formset,
                credit_formset=credit_formset,
                form_errors=[],
            )
            response = HttpResponse(entry_form_html)
            response.headers["HX-Retarget"] = "#form-div"
            return response

        # 3. Validate business rules
        validation_result = validate_journal_entry_balance(
            transaction=transaction,
            debits_data=debit_formset.cleaned_data,
            credits_data=credit_formset.cleaned_data
        )

        if not validation_result.is_valid:
            # Render form with validation errors
            entry_form_html = render_journal_entry_form(
                transaction=transaction,
                debit_formset=debit_formset,
                credit_formset=credit_formset,
                form_errors=validation_result.errors,
            )
            response = HttpResponse(entry_form_html)
            response.headers["HX-Retarget"] = "#form-div"
            return response

        # 4. Save (service handles ALL database operations)
        save_result = save_journal_entry(
            transaction_obj=transaction,
            debits_data=debit_formset.cleaned_data,
            credits_data=credit_formset.cleaned_data,
            paystub_id=metadata_form.cleaned_data.get('paystub_id')
        )

        if not save_result.success:
            # This should rarely happen (validation passed)
            return HttpResponse(f"Error: {save_result.error}", status=500)

        # 5. Build response context via service
        filter_form = TransactionFilterForm(request.POST, prefix="filter")
        current_index = metadata_form.cleaned_data['index']

        context = get_post_save_context(
            filter_form=filter_form,
            current_index=current_index,
            debit_formset=debit_formset,
            credit_formset=credit_formset
        )

        # 6. Render response via helpers
        if context.highlighted_transaction:
            entry_form_html = render_journal_entry_form(
                transaction=context.highlighted_transaction,
                index=context.highlighted_index,
                created_entities=context.created_entities,
            )
        else:
            entry_form_html = ""

        table_html = self.get_table_html(
            transactions=context.transactions,
            index=context.highlighted_index,
            row_url=reverse("journal-entries")
        )
        paystubs_table_html = render_paystubs_table()

        html = render_to_string(self.view_template, {
            "table": table_html,
            "entry_form": entry_form_html,
            "index": context.highlighted_index,
            "transaction_id": context.highlighted_transaction.pk if context.highlighted_transaction else None,
            "paystubs_table": paystubs_table_html,
        })

        return HttpResponse(html)
```

**Result**: 120 lines → ~90 lines, but much cleaner with explicit dependencies

### Phase 4: Remove JournalEntryViewMixin

**File**: `api/views/mixins.py`

Delete the entire `JournalEntryViewMixin` class - all logic moved to helpers/services.

**Before removal, update all views that used the mixin:**

Views that need updating:
1. `JournalEntryTableView` - Remove `JournalEntryViewMixin`, use helpers
2. `JournalEntryFormView` - Remove `JournalEntryViewMixin`, use helpers
3. `PaystubTableView` - Remove `JournalEntryViewMixin`, use helpers
4. `JournalEntryView` - Already updated in Phase 3

Example transformation for `JournalEntryFormView`:

**Before:**
```python
class JournalEntryFormView(
    TransactionsViewMixin, JournalEntryViewMixin, LoginRequiredMixin, View
):
    def get(self, request, transaction_id):
        transaction = Transaction.objects.select_related("journal_entry").get(
            pk=transaction_id
        )
        paystub_id = request.GET.get("paystub_id")
        entry_form_html = self.get_journal_entry_form_html(
            transaction=transaction,
            index=request.GET.get("row_index"),
            paystub_id=paystub_id,
        )
        return HttpResponse(entry_form_html)
```

**After:**
```python
from api.views.journal_entry_helpers import render_journal_entry_form

class JournalEntryFormView(TransactionsViewMixin, LoginRequiredMixin, View):
    def get(self, request, transaction_id):
        transaction = Transaction.objects.select_related("journal_entry").get(
            pk=transaction_id
        )
        paystub_id = request.GET.get("paystub_id")
        entry_form_html = render_journal_entry_form(
            transaction=transaction,
            index=int(request.GET.get("row_index", 0)),
            paystub_id=paystub_id,
        )
        return HttpResponse(entry_form_html)
```

**After all views updated, delete `JournalEntryViewMixin` class entirely.**

### Phase 5: Clean Up Other Views

**File**: `api/views/journal_entry_views.py`

Apply pattern to `TriggerAutoTagView`:

**Before:**
```python
def get(self, request):
    open_transactions = Transaction.objects.filter(is_closed=False)
    Transaction.apply_autotags(open_transactions)
    open_transactions.bulk_update(
        open_transactions,
        ["suggested_account", "prefill", "type", "suggested_entity"],
    )
    return HttpResponse("<small class=text-success>Autotag complete</small>")
```

**After:**
```python
# In journal_entry_services.py
def apply_autotags_to_open_transactions() -> int:
    """
    Applies autotags to all open transactions.
    Returns count of updated transactions.
    """
    open_transactions = Transaction.objects.filter(is_closed=False)
    Transaction.apply_autotags(open_transactions)
    open_transactions.bulk_update(
        open_transactions,
        ["suggested_account", "prefill", "type", "suggested_entity"],
    )
    return open_transactions.count()

# In view
def get(self, request):
    count = apply_autotags_to_open_transactions()
    return HttpResponse(f"<small class=text-success>Autotag complete ({count} transactions)</small>")
```

## Testing Strategy

### Unit Tests (New)
Add tests for new service functions:

```python
# api/tests/services/test_journal_entry_services.py
class TestValidateJournalEntryBalance:
    def test_valid_balanced_entry(self):
        # Test successful validation

    def test_unbalanced_debits_credits(self):
        # Test error when totals don't match

    def test_missing_transaction_match(self):
        # Test error when no item matches transaction

class TestSaveJournalEntry:
    def test_creates_journal_entry(self):
        # Test JournalEntry creation

    def test_creates_new_items(self):
        # Test bulk_create for new items

    def test_updates_existing_items(self):
        # Test bulk_update for changed items

    def test_closes_transaction(self):
        # Test transaction.close() called

    def test_links_paystub(self):
        # Test paystub linking

    def test_atomic_rollback_on_error(self):
        # Test transaction rollback on error
```

### Integration Tests (Existing)
Existing view tests should continue to pass with minimal changes.

## Files to Modify

1. ✏️ `api/services/journal_entry_services.py` - Add new service functions (350 lines added)
2. 🆕 `api/views/journal_entry_helpers.py` - New helper functions for HTML rendering (150 lines)
3. ✏️ `api/views/journal_entry_views.py` - Simplify all views, remove mixin usage (120 → 90 lines for post())
4. 🗑️ `api/views/mixins.py` - Delete `JournalEntryViewMixin` class entirely
5. 🆕 `api/tests/services/test_journal_entry_services.py` - New service unit tests
6. 🆕 `api/tests/views/test_journal_entry_helpers.py` - New helper unit tests
7. ⚠️ `api/tests/views/` - Update existing view tests if needed

## Migration Path

1. **Phase 1**: Add new service functions (non-breaking, pure additions)
2. **Phase 2**: Create helper functions file (non-breaking, pure additions)
3. **Phase 3**: Update JournalEntryView.post() to use services and helpers
4. **Phase 4**: Update remaining views to use helpers, then delete mixin
5. **Phase 5**: Clean up TriggerAutoTagView and other simple views
6. **Phase 6**: Run full test suite
7. **Phase 7**: Manual testing of journal entry workflow
8. **Phase 8**: Add unit tests for new service and helper functions

## Success Criteria

✅ JournalEntryView.post() reduced from 120 to ~90 lines (cleaner, more explicit)
✅ All database writes happen in services (atomic transactions)
✅ JournalEntryViewMixin completely removed
✅ HTML rendering moved to pure helper functions
✅ Service functions are unit testable without HTTP mocking
✅ Helper functions are unit testable with simple data structures
✅ Views only handle HTTP orchestration
✅ Forms continue to handle field validation
✅ Explicit imports - no inheritance magic
✅ All existing tests pass
✅ No change to user-facing behavior

## Future Improvements

After this refactoring:
- Other view files can follow same pattern
- Services can be reused for API endpoints
- Easier to add background job processing
- Business logic centralized and documented
