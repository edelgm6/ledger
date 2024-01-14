import factory
from api.models import Account, CSVProfile, Transaction, Amortization, Reconciliation, JournalEntry, JournalEntryItem, AutoTag, Prefill, PrefillItem, TaxCharge

# CSVProfile Factory
class CSVProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CSVProfile

    name = factory.Faker('word')
    # Add other fields here based on the actual model definition

# Account Factory
class AccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Account

    name = factory.Sequence(lambda n: f"Account {n}")
    type = factory.Iterator(Account.Type.choices, getter=lambda c: c[0])
    sub_type = factory.Iterator(Account.SubType.choices, getter=lambda c: c[0])
    csv_profile = factory.SubFactory(CSVProfileFactory)
    special_type = None
    is_closed = factory.Faker('boolean')

# Transaction Factory
class TransactionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Transaction

    date = factory.Faker('date_object')
    account = factory.SubFactory(AccountFactory)
    amount = factory.Faker('pydecimal', left_digits=5, right_digits=2, positive=True)
    description = factory.Faker('sentence')
    category = factory.Faker('word')
    is_closed = factory.Faker('boolean')
    date_closed = factory.Maybe('is_closed', yes_declaration=factory.Faker('date_object'), no_declaration=None)
    suggested_account = factory.SubFactory(AccountFactory)
    type = factory.Iterator(Transaction.TransactionType.choices, getter=lambda c: c[0])
    linked_transaction = None # To be set manually if needed
    amortization = None  # To be set manually if needed
    prefill = None  # To be set manually if needed

# Amortization Factory
class AmortizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Amortization

    accrued_transaction = factory.SubFactory(TransactionFactory)
    amount = factory.Faker('pydecimal', left_digits=10, right_digits=2, positive=True)
    periods = factory.Faker('random_int', min=1, max=12)
    is_closed = factory.Faker('boolean')
    description = factory.Faker('sentence')
    suggested_account = factory.SubFactory(AccountFactory)

# Reconciliation Factory
class ReconciliationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Reconciliation

    account = factory.SubFactory(AccountFactory)
    date = factory.Faker('date_object')
    amount = factory.Faker('pydecimal', left_digits=10, right_digits=2, positive=True)
    transaction = factory.SubFactory(TransactionFactory)

# JournalEntry Factory
class JournalEntryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = JournalEntry

    date = factory.Faker('date_object')
    description = factory.Faker('sentence')
    transaction = factory.SubFactory(TransactionFactory)

# JournalEntryItem Factory
class JournalEntryItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = JournalEntryItem

    journal_entry = factory.SubFactory(JournalEntryFactory)
    type = factory.Iterator(JournalEntryItem.JournalEntryType.choices, getter=lambda c: c[0])
    amount = factory.Faker('pydecimal', left_digits=10, right_digits=2, positive=True)
    account = factory.SubFactory(AccountFactory)

# Prefill Factory
class PrefillFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Prefill

    name = factory.Faker('word')

# PrefillItem Factory
class PrefillItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PrefillItem

    prefill = factory.SubFactory(PrefillFactory)
    account = factory.SubFactory(AccountFactory)
    journal_entry_item_type = factory.Iterator(JournalEntryItem.JournalEntryType.choices, getter=lambda c: c[0])
    order = factory.Sequence(lambda n: n)

# AutoTag Factory
class AutoTagFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AutoTag

    search_string = factory.Faker('word')
    account = factory.SubFactory(AccountFactory)
    transaction_type = factory.Iterator(Transaction.TransactionType.choices, getter=lambda c: c[0], cycle=True)
    prefill = factory.SubFactory(PrefillFactory)

# TaxCharge Factory
class TaxChargeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TaxCharge

    type = factory.Iterator(TaxCharge.Type.choices, getter=lambda c: c[0])
    transaction = factory.SubFactory(TransactionFactory)
    date = factory.Faker('date_object')
    amount = factory.Faker('pydecimal', left_digits=10, right_digits=2, positive=True)

