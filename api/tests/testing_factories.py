import datetime
from decimal import Decimal

import factory
from api.models import Account, CSVProfile, Entity, Transaction, Amortization, Reconciliation, JournalEntry, JournalEntryItem, AutoTag, Prefill, TaxCharge, Loan, LoanPayment


# Entity Factory
class EntityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Entity

    name = factory.Sequence(lambda n: f"Entity {n}")
    is_closed = False

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
    is_closed = False
    date_closed = factory.Maybe('is_closed', yes_declaration=factory.Faker('date_object'), no_declaration=None)
    suggested_account = None
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
    created_by = "user"

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


# Loan Factory
class LoanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Loan

    name = factory.Sequence(lambda n: f"Loan {n}")
    original_amount = Decimal("300000.00")
    annual_interest_rate = Decimal("0.0650")
    term_months = 360
    start_date = factory.LazyFunction(lambda: datetime.date(2026, 7, 1))
    payment_amount = None
    principal_account = factory.SubFactory(
        AccountFactory, type=Account.Type.LIABILITY,
        sub_type=Account.SubType.LONG_TERM_DEBT, is_closed=False,
    )
    interest_account = factory.SubFactory(
        AccountFactory, type=Account.Type.EXPENSE,
        sub_type=Account.SubType.INTEREST, is_closed=False,
    )
    payment_account = None
    description_match = ""
    date_window_days = 7
    entity = None
    is_closed = False


# LoanPayment Factory
class LoanPaymentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LoanPayment

    loan = factory.SubFactory(LoanFactory)
    sequence = factory.Sequence(lambda n: n + 1)
    date = factory.LazyFunction(lambda: datetime.date(2026, 7, 1))
    payment_amount = Decimal("1896.20")
    principal_amount = Decimal("271.20")
    interest_amount = Decimal("1625.00")
    remaining_balance = Decimal("299728.80")
    kind = LoanPayment.Kind.SCHEDULED
    transaction = None

