import calendar
import datetime
import math
import re
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from api.aws_services import (
    clean_and_convert_string_to_decimal,
    clean_string,
    convert_table_to_cleaned_dataframe,
    create_textract_job,
    get_textract_results,
)
from api.utils import parse_currency, short_error_label
from api.validators import non_zero


class Entity(models.Model):
    name = models.CharField(max_length=200, unique=True)
    is_closed = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "entities"
        ordering = ["is_closed", "name"]

    def __str__(self):
        return self.name


class S3File(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETE = "COMPLETE", "Complete"
        FAILED = "FAILED", "Failed"

    prefill = models.ForeignKey("Prefill", on_delete=models.PROTECT)
    url = models.URLField(max_length=200, unique=True)
    user_filename = models.CharField(max_length=200)
    s3_filename = models.CharField(max_length=200)
    textract_job_id = models.CharField(max_length=200)
    analysis_complete = models.DateTimeField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error_message = models.TextField(blank=True, default="")

    def __str__(self):
        return self.prefill.name + " " + self.s3_filename

    @property
    def short_error(self) -> str:
        """A compact, human-friendly label for the stored error_message."""
        return short_error_label(self.error_message)

    def create_textract_job(self):
        job_id = create_textract_job(filename=self.s3_filename)
        self.textract_job_id = job_id
        self.save()
        return job_id

    def create_paystubs_from_textract_data(self):
        textract_data = self._extract_data()
        for page_id, page_data in textract_data.items():
            try:
                company_name = page_data["Company"]
            except KeyError:
                company_name = self.prefill.name
            paystub = Paystub.objects.create(
                document=self,
                page_id=page_id,
                title=company_name + " " + page_data["End Period"],
            )
            paystub_values = []
            for account, value in page_data.items():
                if not isinstance(account, Account):
                    continue
                amount = value["value"]
                if amount != 0:
                    paystub_values.append(
                        PaystubValue(
                            paystub=paystub,
                            account=account,
                            amount=amount,
                            journal_entry_item_type=value["entry_type"],
                            entity=value["entity"],
                        )
                    )
            PaystubValue.objects.bulk_create(paystub_values)

    def _extract_data(self):
        from textractor.entities.document import Document

        textract_job_response = get_textract_results(job_id=self.textract_job_id)

        # Load the Textract response from the JSON file using textractor
        document = Document.open(textract_job_response)

        # Step 1: Build pages data structure
        page_ids = []
        data = {}
        for page in document.pages:
            page_id = page.id
            page_ids.append(page_id)
            data[page_id] = {}

        # Step 2: Name each page and create a data structure
        # Extract key-value pairs
        key_value_pairs = document.key_values

        # Print the key-value pairs and create data object
        keyword_searches = DocSearch.objects.filter(
            keyword__isnull=False, prefill=self.prefill
        )

        for kv in key_value_pairs:
            key = clean_string(kv.key.text)
            # print(key)
            # print(kv.value.text)
            for keyword_search in keyword_searches:
                if key == keyword_search.keyword:
                    identifier = keyword_search.get_selection_or_account()
                    # Keyword searches can look for dollars or strings and need
                    # to be treated differently for each
                    if isinstance(identifier, Account):
                        data[kv.page_id][identifier] = {}
                        data[kv.page_id][identifier]["value"] = (
                            clean_and_convert_string_to_decimal(kv.value.text)
                        )
                        data[kv.page_id][identifier]["entry_type"] = (
                            keyword_search.journal_entry_item_type
                        )
                        data[kv.page_id][identifier]["entity"] = keyword_search.entity
                    else:
                        data[kv.page_id][identifier] = clean_string(kv.value.text)

        # Step 3: Grab table data from tables
        table_searches = DocSearch.objects.filter(
            keyword__isnull=True, prefill=self.prefill
        )
        for table in document.tables:
            # print(table.get_text_and_words())
            for table_search in table_searches:
                table_title = table.title if table.title is None else table.title.text
                both_table_names_none_condition = (
                    table_search.table_name is None and table_title is None
                )
                table_names_equal_condition = table_search.table_name == clean_string(
                    table_title
                )

                if not (both_table_names_none_condition or table_names_equal_condition):
                    continue

                pandas_table = convert_table_to_cleaned_dataframe(table)
                try:
                    value = pandas_table.loc[table_search.row, table_search.column]
                except KeyError:
                    continue

                value = clean_and_convert_string_to_decimal(value)
                identifier = table_search.get_selection_or_account()
                if identifier in data[table.page_id]:
                    data[table.page_id][identifier]["value"] += value
                else:
                    data[table.page_id][identifier] = {}
                    data[table.page_id][identifier]["value"] = value
                    data[table.page_id][identifier]["entry_type"] = (
                        table_search.journal_entry_item_type
                    )
                    data[table.page_id][identifier]["entity"] = table_search.entity

        return data


class Amortization(models.Model):
    accrued_journal_entry_item = models.OneToOneField(
        "JournalEntryItem", on_delete=models.CASCADE, related_name="amortization"
    )
    amount = models.DecimalField(decimal_places=2, max_digits=12)
    salvage_value = models.DecimalField(
        decimal_places=2, max_digits=12, null=True, blank=True
    )
    periods = models.PositiveSmallIntegerField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)
    description = models.CharField(max_length=200)
    suggested_account = models.ForeignKey("Account", on_delete=models.PROTECT)
    entity = models.ForeignKey(
        "Entity", related_name="amortizations", on_delete=models.PROTECT, null=True
    )

    def __str__(self):
        return self.description + " $" + str(self.amount)

    @property
    def is_depreciation(self):
        return self.salvage_value is not None

    @property
    def depreciable_base(self):
        return self.amount - (self.salvage_value or 0)

    @staticmethod
    def _round_down(n, decimals=2):
        multiplier = 10**decimals
        return math.floor(n * multiplier) / multiplier

    def get_related_transactions(self):
        return self.transactions.all().order_by("-date")

    def get_remaining_balance_and_periods_and_max_date(self):
        related_transactions = self.get_related_transactions()
        total_amortized = sum(
            [transaction.amount for transaction in related_transactions]
        )
        remaining_balance = self.depreciable_base + total_amortized

        related_transactions_count = len(related_transactions)
        remaining_periods = self.periods - related_transactions_count

        max_date = related_transactions[0].date if related_transactions else ""

        return remaining_balance, remaining_periods, max_date

    def amortize(self, date):
        starting_amortization_count = len(self.get_related_transactions())

        if self.periods - starting_amortization_count == 0 or self.is_closed:
            raise ValidationError("Cannot further amortize")
        elif self.periods - starting_amortization_count == 1:
            amortization_amount, _, _ = (
                self.get_remaining_balance_and_periods_and_max_date()
            )
            is_final_amortization = True
        else:
            amortization_amount = self._round_down(
                self.depreciable_base / self.periods
            )
            is_final_amortization = False

        label = "depreciation" if self.is_depreciation else "amortization"

        transaction = Transaction.objects.create(
            date=date,
            account=self.accrued_journal_entry_item.account,
            amount=amortization_amount * -1,
            description=(
                self.description
                + " "
                + label
                + " #"
                + str(len(self.get_related_transactions()) + 1)
            ),
            suggested_account=self.suggested_account,
            suggested_entity=self.entity,
            type=Transaction.TransactionType.PURCHASE,
            amortization=self,
        )

        if is_final_amortization:
            self.is_closed = True
            self.save()
        return transaction


class Reconciliation(models.Model):
    account = models.ForeignKey("Account", on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(decimal_places=2, max_digits=12, null=True, blank=True)
    transaction = models.OneToOneField(
        "Transaction", on_delete=models.PROTECT, null=True, blank=True
    )

    class Meta:
        unique_together = [["account", "date"]]

    def __str__(self):
        return str(self.date) + " " + self.account.name

    def plug_investment_change(self):
        if not self.account.is_investment:
            raise ValidationError(
                f"Cannot plug a gain/loss for {self.account.name}: reconciliation "
                "gain/loss plugs mark an account to unrealized investment gains, "
                "which is only valid for investment accounts (securities, real "
                "estate, vehicles). Marking any other account breaks the "
                "cash-flow reconciliation."
            )

        GAIN_LOSS_ACCOUNT = Account.objects.get(
            special_type=Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES
        )

        transaction_amount = (
            self.transaction.amount if self.transaction is not None else 0
        )
        account_balance = self.account.get_balance(self.date)
        delta = self.amount - (account_balance - transaction_amount)

        if self.transaction:
            transaction = self.transaction
            transaction.amount = delta
            transaction.save()
        else:
            transaction = Transaction.objects.create(
                date=self.date,
                amount=delta,
                account=self.account,
                description=(
                    str(self.date) + " Plug gain/loss for " + self.account.name
                ),
            )
            self.transaction = transaction
            self.save()

        try:
            journal_entry = transaction.journal_entry
        except JournalEntry.DoesNotExist:
            journal_entry = JournalEntry.objects.create(
                date=self.date,
                description=transaction.description,
                transaction=transaction,
            )

        if delta > 0:
            gain_loss_entry_type = JournalEntryItem.JournalEntryType.CREDIT
            account_entry_type = JournalEntryItem.JournalEntryType.DEBIT
        else:
            gain_loss_entry_type = JournalEntryItem.JournalEntryType.DEBIT
            account_entry_type = JournalEntryItem.JournalEntryType.CREDIT

        journal_entry_items = JournalEntryItem.objects.filter(
            journal_entry=journal_entry
        )
        journal_entry_items.delete()

        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=gain_loss_entry_type,
            amount=abs(delta),
            account=GAIN_LOSS_ACCOUNT,
            entity=self.account.entity,
        )

        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=account_entry_type,
            amount=abs(delta),
            account=self.account,
            entity=self.account.entity,
        )

        transaction.close()

        return journal_entry


class TransactionQuerySet(models.QuerySet):
    def filter_for_table(
        self,
        is_closed=None,
        has_linked_transaction=None,
        transaction_types=None,
        accounts=None,
        date_from=None,
        date_to=None,
        related_accounts=None,
    ):
        queryset = self
        if is_closed is not None:
            queryset = queryset.filter(is_closed=is_closed)
        if has_linked_transaction is not None:
            queryset = queryset.exclude(
                linked_transaction__isnull=has_linked_transaction
            )
        if transaction_types:
            queryset = queryset.filter(type__in=transaction_types)
        if accounts:
            queryset = queryset.filter(account__in=accounts)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        if related_accounts:
            queryset = queryset.filter(
                journal_entry__journal_entry_items__account__in=related_accounts
            ).distinct()
        return queryset.order_by("date", "account", "pk")


class TransactionManager(models.Manager):
    def get_queryset(self):
        return TransactionQuerySet(self.model, using=self._db)

    def filter_for_table(self, *args, **kwargs):
        return self.get_queryset().filter_for_table(*args, **kwargs)


class Transaction(models.Model):
    class TransactionType(models.TextChoices):
        INCOME = "income", _("Income")
        PURCHASE = "purchase", _("Purchase")
        PAYMENT = "payment", _("Payment")
        TRANSFER = "transfer", _("Transfer")

    date = models.DateField()
    account = models.ForeignKey("Account", on_delete=models.PROTECT)
    amount = models.DecimalField(decimal_places=2, max_digits=12, validators=[non_zero])
    description = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=200, blank=True)
    is_closed = models.BooleanField(default=False)
    date_closed = models.DateField(null=True, blank=True)
    suggested_account = models.ForeignKey(
        "Account",
        related_name="suggested_account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    suggested_entity = models.ForeignKey(
        "Entity",
        related_name="suggested_entity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    type = models.CharField(max_length=25, choices=TransactionType.choices)
    linked_transaction = models.OneToOneField(
        "Transaction", on_delete=models.SET_NULL, null=True, blank=True
    )
    prefill = models.ForeignKey(
        "Prefill", on_delete=models.PROTECT, null=True, blank=True
    )
    amortization = models.ForeignKey(
        "Amortization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transactions",
    )

    objects = TransactionManager()

    class Meta:
        indexes = [
            models.Index(fields=["date"], name="date_idx"),
            models.Index(fields=["account"], name="account_idx"),
            models.Index(fields=["type"], name="type_idx"),
            models.Index(fields=["is_closed"], name="is_closed_idx"),
            models.Index(fields=["linked_transaction"], name="linked_transaction_idx"),
        ]

    def __str__(self):
        return (
            str(self.date)
            + " "
            + self.account.name
            + " "
            + self.description
            + " $"
            + str(self.amount)
        )

    def close(self, date=None):
        if not date:
            date = datetime.date.today()
        self.is_closed = True
        self.date_closed = date
        self.save()

    def create_link(self, transaction):
        self.linked_transaction = transaction
        self.suggested_account = transaction.account
        self.suggested_entity = transaction.account.entity
        self.save()
        transaction.close()

    @staticmethod
    def apply_autotags(transactions):
        all_tags = AutoTag.objects.all()
        for transaction in transactions:
            cleaned_description = re.sub(
                " +", " ", transaction.description.strip().lower()
            )

            for tag in all_tags:
                if tag.search_string.lower() in cleaned_description:
                    transaction.suggested_account = tag.account
                    transaction.suggested_entity = tag.entity
                    transaction.prefill = tag.prefill
                    if tag.transaction_type:
                        transaction.type = tag.transaction_type
                    else:
                        transaction.type = Transaction.TransactionType.PURCHASE
                    break


class TaxCharge(models.Model):
    class Type(models.TextChoices):
        PROPERTY = "property", _("Property")
        FEDERAL = "federal", _("Federal")
        STATE = "state", _("State")

    # type = models.CharField(max_length=25, choices=Type.choices)
    account = models.ForeignKey(
        "Account", related_name="tax_charges", on_delete=models.PROTECT
    )
    transaction = models.OneToOneField("Transaction", on_delete=models.PROTECT)
    date = models.DateField()
    amount = models.DecimalField(decimal_places=2, max_digits=12)

    class Meta:
        unique_together = [["account", "date"]]

    def __str__(self):
        account_name = self.account.name if self.account else "No Account"
        return f"{self.date} {account_name}"

    def save(self, *args, **kwargs):
        try:
            transaction = self.transaction
            transaction.amount = self.amount
            transaction.save()
        except Transaction.DoesNotExist:
            transaction = Transaction.objects.create(
                date=self.date,
                account=self.account,
                amount=self.amount,
                description=str(self.date) + " " + self.account.name,
                is_closed=True,
                date_closed=datetime.date.today(),
                type=Transaction.TransactionType.PURCHASE,
            )
            self.transaction = transaction

        try:
            journal_entry = self.transaction.journal_entry
        except JournalEntry.DoesNotExist:
            journal_entry = JournalEntry.objects.create(
                date=self.date, transaction=self.transaction
            )
        journal_entry.delete_journal_entry_items()

        tax_payable_account = self.account.tax_payable_account
        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=self.transaction.amount,
            account=self.account,
            entity=self.account.entity,
        )
        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=self.transaction.amount,
            account=tax_payable_account,
            entity=tax_payable_account.entity,
        )

        # Update the Reconciliation per the new tax amount
        liability_balance = tax_payable_account.get_balance(self.date)
        try:
            reconciliation = Reconciliation.objects.get(
                date=self.date, account=tax_payable_account
            )
            reconciliation.amount = liability_balance
            reconciliation.save()
        except Reconciliation.DoesNotExist:
            pass

        super().save(*args, **kwargs)


class Account(models.Model):
    class SpecialType(models.TextChoices):
        UNREALIZED_GAINS_AND_LOSSES = (
            "unrealized_gains_and_losses",
            _("Unrealized Gains and Losses"),
        )
        STATE_TAXES_PAYABLE = "state_taxes_payable", _("State Taxes Payable")
        FEDERAL_TAXES_PAYABLE = ("federal_taxes_payable", _("Federal Taxes Payable"))
        PROPERTY_TAXES_PAYABLE = ("property_taxes_payable", _("Property Taxes Payable"))
        STATE_TAXES = "state_taxes", _("State Taxes")
        FEDERAL_TAXES = "federal_taxes", _("Federal Taxes")
        PROPERTY_TAXES = "property_taxes", _("Property Taxes")
        PAYROLL_TAXES = "payroll_taxes", _("Payroll Taxes")
        WALLET = "wallet", _("Wallet")
        PREPAID_EXPENSES = "prepaid_expenses", _("Prepaid Expenses")
        STARTING_EQUITY = "starting_equity", _("Starting Equity")

    class Type(models.TextChoices):
        ASSET = "asset", _("Asset")
        LIABILITY = "liability", _("Liability")
        INCOME = "income", _("Income")
        EXPENSE = "expense", _("Expense")
        EQUITY = "equity", _("Equity")

    class SubType(models.TextChoices):
        # Liability types
        SHORT_TERM_DEBT = "short_term_debt", _("Short-term Debt")
        TAXES_PAYABLE = "taxes_payable", _("Taxes Payable")
        LONG_TERM_DEBT = "long_term_debt", _("Long-term Debt")
        # Asset types
        CASH = "cash", _("Cash")
        ACCOUNTS_RECEIVABLE = "accounts_receivable", _("Accounts Receivable")
        PREPAID_EXPENSES = "prepaid_expenses", _("Prepaid Expenses")
        SECURITIES_UNRESTRICTED = (
            "securities_unrestricted",
            _("Securities-Unrestricted"),
        )
        SECURITIES_RESTRICTED = ("securities_restricted", _("Securities-Restricted"))
        REAL_ESTATE = "real_estate", _("Real Estate")
        VEHICLES = "vehicles", _("Vehicles")
        # Equity types
        RETAINED_EARNINGS = "retained_earnings", _("Retained Earnings")
        # Income types
        SALARY = "salary", _("Salary")
        DIVIDENDS_AND_INTEREST = ("dividends_and_interest", _("Dividends & Interest"))
        REALIZED_INVESTMENT_GAINS = (
            "realized_investment_gains",
            _("Realized Investment Gains"),
        )
        OTHER_INCOME = "other_income", _("Other Income")
        UNREALIZED_INVESTMENT_GAINS = (
            "unrealized_investment_gains",
            _("Unrealized Investment Gains"),
        )
        # Expense Types
        OPERATING = "operating", _("Operating")
        TAX = "tax", _("Tax")
        INTEREST = "interest", _("Interest Expense")

    # TODO: Add a test that makes sure every type/subtype is represented here
    SUBTYPE_TO_TYPE_MAP = {
        Type.LIABILITY: [
            SubType.SHORT_TERM_DEBT,
            SubType.TAXES_PAYABLE,
            SubType.LONG_TERM_DEBT,
        ],
        Type.ASSET: [
            SubType.CASH,
            SubType.ACCOUNTS_RECEIVABLE,
            SubType.PREPAID_EXPENSES,
            SubType.SECURITIES_UNRESTRICTED,
            SubType.SECURITIES_RESTRICTED,
            SubType.REAL_ESTATE,
            SubType.VEHICLES,
        ],
        Type.EQUITY: [SubType.RETAINED_EARNINGS],
        Type.INCOME: [
            SubType.SALARY,
            SubType.DIVIDENDS_AND_INTEREST,
            SubType.REALIZED_INVESTMENT_GAINS,
            SubType.OTHER_INCOME,
            SubType.UNREALIZED_INVESTMENT_GAINS,
        ],
        Type.EXPENSE: [SubType.OPERATING, SubType.INTEREST, SubType.TAX],
    }

    # Asset classes carried at fair value, whose balance changes can be non-cash
    # marks (unrealized gains/losses). The cash flow statement excludes these
    # marks from investing (get_cash_from_investing_balances) and from net income
    # (net_income_less_gains_and_losses), so a mark cancels out cleanly. Marking
    # any *other* account to unrealized gains has no such offset and breaks the
    # cash-flow reconciliation, so plug_investment_change is restricted to this
    # set.
    INVESTMENT_SUB_TYPES = [
        SubType.SECURITIES_UNRESTRICTED,
        SubType.SECURITIES_RESTRICTED,
        SubType.REAL_ESTATE,
        SubType.VEHICLES,
    ]

    # Income taxes for the post-tax savings rate: federal, state, and payroll
    # withholding. Property tax is intentionally excluded — it isn't income-based.
    # (Distinct from tax_services.get_tax_accounts, which covers the manually
    # charged taxes — federal, state, property — and excludes payroll.)
    INCOME_TAX_SPECIAL_TYPES = (
        SpecialType.FEDERAL_TAXES,
        SpecialType.STATE_TAXES,
        SpecialType.PAYROLL_TAXES,
    )

    name = models.CharField(max_length=200, unique=True)
    type = models.CharField(max_length=9, choices=Type.choices)
    sub_type = models.CharField(max_length=30, choices=SubType.choices)
    csv_profile = models.ForeignKey(
        "CSVProfile",
        related_name="accounts",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    special_type = models.CharField(
        max_length=30, choices=SpecialType.choices, null=True, blank=True
    )
    is_closed = models.BooleanField(default=False)
    is_depreciation = models.BooleanField(
        default=False,
        help_text=(
            "Marks an expense account as depreciation. Depreciation draws a "
            "depreciable asset down without moving cash, so the cash flow "
            "statement adds it back to operations and keeps it out of investing."
        ),
    )
    entity = models.ForeignKey(
        "Entity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounts",
    )
    tax_payable_account = models.OneToOneField(
        "Account", on_delete=models.SET_NULL, null=True, blank=True
    )
    tax_rate = models.DecimalField(
        max_digits=4,  # enough to store 999.9999 if needed
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Tax rate as a decimal (e.g., 0.3110 for 31.10%)",
    )
    tax_amount = models.DecimalField(
        max_digits=12,  # depends on how big flat amounts can be
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Flat tax amount (e.g., 1000.00)",
    )

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=["special_type"],
                condition=~Q(
                    special_type__in=[
                        "property_taxes",
                        "prepaid_expenses",
                        "payroll_taxes",
                    ]
                ),
                name="unique_special_type_except_property_taxes",
            )
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()

        if self.tax_rate is not None and self.tax_amount is not None:
            raise ValidationError("Only one of tax_rate or tax_amount can be set.")

    @property
    def is_investment(self):
        return self.sub_type in Account.INVESTMENT_SUB_TYPES

    @staticmethod
    def get_balance_from_debit_and_credit(account_type, debits, credits):
        DEBITS_INCREASE_ACCOUNTS = [Account.Type.ASSET, Account.Type.EXPENSE]
        if account_type in DEBITS_INCREASE_ACCOUNTS:
            return debits - credits
        else:
            return credits - debits

    def get_balance(self, end_date, start_date=None):
        INCOME_STATEMENT_ACCOUNT_TYPES = ["income", "expense"]

        journal_entry_items = JournalEntryItem.objects.filter(
            journal_entry__date__lte=end_date, account=self
        )

        if self.type in INCOME_STATEMENT_ACCOUNT_TYPES:
            journal_entry_items = journal_entry_items.filter(
                journal_entry__date__gte=start_date,
            )

        debits = 0
        credits = 0
        for journal_entry_item in journal_entry_items:
            amount = journal_entry_item.amount

            journal_entry_type = JournalEntryItem.JournalEntryType.DEBIT
            if journal_entry_item.type == journal_entry_type:
                debits += amount
            else:
                credits += amount

        return Account.get_balance_from_debit_and_credit(
            account_type=self.type, debits=debits, credits=credits
        )


class JournalEntry(models.Model):
    date = models.DateField()
    description = models.CharField(max_length=200, blank=True)
    transaction = models.OneToOneField(
        "Transaction", related_name="journal_entry", on_delete=models.CASCADE
    )
    created_by = models.CharField(max_length=100, default="user")

    class Meta:
        verbose_name_plural = "journal entries"

    def __str__(self):
        return str(self.pk) + ": " + str(self.date) + " " + self.description

    def delete(self, *args, **kwargs):
        self.transaction.is_closed = False
        self.transaction.date_closed = None
        self.transaction.save()
        super().delete(*args, **kwargs)

    def delete_journal_entry_items(self):
        journal_entry_items = JournalEntryItem.objects.filter(journal_entry=self)
        journal_entry_items.delete()


class JournalEntryItemQuerySet(models.QuerySet):
    def filter_for_recharacterize(
        self,
        description=None,
        date_from=None,
        date_to=None,
        accounts=None,
        entities=None,
        entity_is_empty=None,
        entry_type=None,
    ):
        """Selects the universe of journal entry items to recharacterize.

        Mirrors TransactionQuerySet.filter_for_table: each argument is optional
        and only narrows the queryset when provided. ``description`` matches the
        parent transaction's description; ``date_from``/``date_to`` bound the
        journal entry date; ``accounts``/``entities`` (lists) match the item's own
        account/entity (any of them); ``entity_is_empty`` matches items with no
        entity; ``entry_type`` is "debit" or "credit".
        """
        queryset = self
        if description:
            queryset = queryset.filter(
                journal_entry__transaction__description__icontains=description
            )
        if date_from:
            queryset = queryset.filter(journal_entry__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(journal_entry__date__lte=date_to)
        if accounts:
            queryset = queryset.filter(account__in=accounts)
        if entities:
            queryset = queryset.filter(entity__in=entities)
        if entity_is_empty:
            queryset = queryset.filter(entity__isnull=True)
        if entry_type:
            queryset = queryset.filter(type=entry_type)
        return queryset.select_related(
            "account", "entity", "journal_entry__transaction"
        ).order_by("journal_entry__date", "pk")


class JournalEntryItemManager(models.Manager):
    def get_queryset(self):
        return JournalEntryItemQuerySet(self.model, using=self._db)

    def filter_for_recharacterize(self, *args, **kwargs):
        return self.get_queryset().filter_for_recharacterize(*args, **kwargs)


class JournalEntryItem(models.Model):
    class JournalEntryType(models.TextChoices):
        DEBIT = "debit", _("Debit")
        CREDIT = "credit", _("Credit")

    journal_entry = models.ForeignKey(
        "JournalEntry", related_name="journal_entry_items", on_delete=models.CASCADE
    )
    type = models.CharField(max_length=6, choices=JournalEntryType.choices)
    amount = models.DecimalField(decimal_places=2, max_digits=12, validators=[non_zero])
    account = models.ForeignKey("Account", on_delete=models.PROTECT)
    entity = models.ForeignKey(
        "Entity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal_entry_items",
    )

    objects = JournalEntryItemManager()

    class Meta:
        indexes = [
            models.Index(fields=["type"], name="jei_date_idx"),
            models.Index(fields=["account"], name="jei_account_idx"),
        ]

    def __str__(self):
        return str(self.journal_entry.id) + " " + self.type + " $" + str(self.amount)

    def remove_entity(self):
        self.entity = None
        self.save()

    def get_signed_amount(self):
        """This item's signed contribution to its account's balance.

        Positive when the item increases the account's natural balance,
        negative when it decreases it — the same debit/credit convention used
        for aggregate balances in Account.get_balance_from_debit_and_credit.
        """
        debit = self.amount if self.type == self.JournalEntryType.DEBIT else 0
        credit = self.amount if self.type == self.JournalEntryType.CREDIT else 0
        return Account.get_balance_from_debit_and_credit(
            self.account.type, debits=debit, credits=credit
        )


class AutoTag(models.Model):
    search_string = models.CharField(max_length=20)
    account = models.ForeignKey(
        "Account", on_delete=models.CASCADE, null=True, blank=True
    )
    transaction_type = models.CharField(
        max_length=25, choices=Transaction.TransactionType.choices, blank=True
    )
    prefill = models.ForeignKey(
        "Prefill", on_delete=models.CASCADE, null=True, blank=True
    )
    entity = models.ForeignKey(
        "Entity", on_delete=models.CASCADE, null=True, blank=True
    )

    def __str__(self):
        return '"' + self.search_string + '": ' + str(self.account)


class Prefill(models.Model):
    name = models.CharField(max_length=200)
    is_closed = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Paystub(models.Model):
    document = models.ForeignKey(
        "S3File", on_delete=models.CASCADE, related_name="documents"
    )
    page_id = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    journal_entry = models.OneToOneField(
        "JournalEntry", null=True, blank=True, on_delete=models.SET_NULL
    )

    def __str__(self):
        return self.title


class PaystubValue(models.Model):
    paystub = models.ForeignKey(
        "Paystub", on_delete=models.CASCADE, related_name="paystub_values"
    )
    account = models.ForeignKey("Account", on_delete=models.PROTECT)
    amount = models.DecimalField(decimal_places=2, max_digits=12)
    journal_entry_item_type = models.CharField(
        max_length=25, choices=JournalEntryItem.JournalEntryType.choices
    )
    entity = models.ForeignKey(
        "Entity",
        related_name="paystubvalues",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.paystub.title + "-" + self.account.name + "-" + str(self.amount)


class DocSearch(models.Model):
    prefill = models.ForeignKey("Prefill", on_delete=models.PROTECT)
    keyword = models.CharField(max_length=200, null=True, blank=True)
    table_name = models.CharField(max_length=200, null=True, blank=True)
    row = models.CharField(max_length=200, null=True, blank=True)
    column = models.CharField(max_length=200, null=True, blank=True)
    account = models.ForeignKey(
        "Account", null=True, blank=True, on_delete=models.SET_NULL
    )
    journal_entry_item_type = models.CharField(
        max_length=25,
        choices=JournalEntryItem.JournalEntryType.choices,
        blank=True,
        null=True,
    )
    entity = models.ForeignKey(
        "Entity",
        related_name="docsearches",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    STRING_CHOICES = [
        ("Company", "Company"),
        ("Begin Period", "Begin Period"),
        ("End Period", "End Period"),
    ]
    selection = models.CharField(
        max_length=20, choices=STRING_CHOICES, null=True, blank=True
    )

    class Meta:
        verbose_name_plural = "doc searches"

    def __str__(self):
        account_name = self.account.name if self.account is not None else None
        selection_value = self.selection if self.selection is not None else ""
        return self.prefill.name + " " + (account_name or selection_value)

    def clean(self):
        super().clean()

        # Check the existing conditions
        if not self.keyword and (self.row is None or self.column is None):
            error_msg = (
                "Either 'keyword' must be provided, or both "
                "'row' and 'column' must be provided."
            )
            raise ValidationError(error_msg)

        # Ensure either account or selection is set
        if not (self.account and self.journal_entry_item_type) and not self.selection:
            error_msg = (
                "Either 'account' and 'type' must be provided, or "
                "'selection' must be one of the specified choices."
            )
            raise ValidationError(error_msg)

        if self.account and self.selection:
            raise ValidationError(
                "Both 'account' and 'selection' cannot be set at the same time."
            )

    def get_selection_or_account(self):
        if self.selection:
            return self.selection
        return self.account


class CSVColumnValuePair(models.Model):
    column = models.CharField(max_length=200)
    value = models.CharField(max_length=200)


class CSVProfile(models.Model):
    name = models.CharField(max_length=200)
    date = models.CharField(max_length=200)
    description = models.CharField(max_length=200)
    category = models.CharField(max_length=200)
    clear_prepended_until_value = models.CharField(max_length=200, blank=True)
    clear_values_column_pairs = models.ManyToManyField(
        CSVColumnValuePair, blank=True
    )
    inflow = models.CharField(max_length=200)
    outflow = models.CharField(max_length=200)
    date_format = models.CharField(max_length=200, default="%Y-%m-%d")

    def __str__(self):
        return self.name

    def create_transactions_from_csv(self, csv, account):
        rows_cleaned_csv = self._clear_prepended_rows(csv)
        dict_based_csv = self._list_of_lists_to_list_of_dicts(rows_cleaned_csv)
        cleared_rows_csv = self._clear_extraneous_rows(dict_based_csv)

        transactions_list = []
        for row in cleared_rows_csv:
            if row == {}:
                break
            amount = self._get_coalesced_amount(row)
            if amount == 0:
                break

            # Set defaults
            transaction = Transaction(
                date=self._get_formatted_date(row[self.date]),
                account=account,
                amount=amount,
                description=row[self.description],
                category=row[self.category],
                suggested_account=None,  # Default value
                prefill=None,  # Default value
                type=Transaction.TransactionType.PURCHASE,  # Default type
            )
            transactions_list.append(transaction)

        Transaction.apply_autotags(transactions_list)
        created = Transaction.objects.bulk_create(transactions_list)

        # Best-effort bill/loan tagging is applied by the caller (the upload
        # service) via api.services.tagging_services, keeping the models layer
        # free of service imports. Return the created objects so the caller can
        # tag them; callers wanting a count use len(...).
        return created

    def _get_formatted_date(self, date_string):
        # Parse using the profile's input format and return a date object (not a
        # string) so the in-memory Transaction carries the right type for its
        # DateField. Advisory bill/loan tagging does date arithmetic on these
        # objects before they're re-read from the DB, so a str would blow up
        # (same class of bug as _get_coalesced_amount coercing to Decimal).
        return datetime.datetime.strptime(date_string, self.date_format).date()

    def _get_coalesced_amount(self, row):
        # CSV cells are strings; coerce to Decimal so the in-memory Transaction
        # carries the right type (its amount is a DecimalField). Advisory
        # bill/loan tagging runs on these in-memory objects before they're
        # re-read from the DB, and does arithmetic on amount, so a raw string
        # would blow it up. parse_currency also tolerates thousands separators
        # and dollar signs, matching CommaDecimalField.
        raw = row[self.inflow] or row[self.outflow]
        # A blank amount marks the end-of-data row the caller breaks on.
        return parse_currency(raw) if raw else Decimal(0)

    def _clear_prepended_rows(self, csv_data):
        if not self.clear_prepended_until_value:
            return csv_data

        target_row_index = None
        for i, row in enumerate(csv_data):
            if self.clear_prepended_until_value in row:
                target_row_index = i
                break

        if target_row_index is not None:
            del csv_data[:target_row_index]

        return csv_data

    def _list_of_lists_to_list_of_dicts(self, list_of_lists):
        column_headings = list_of_lists[0]
        trimmed_headings = [heading.strip() for heading in column_headings]
        list_of_dicts = [dict(zip(trimmed_headings, row)) for row in list_of_lists[1:]]
        return list_of_dicts

    def _clear_extraneous_rows(self, rows_list):
        cleaned_rows = []
        for row in rows_list:
            include_row = True
            for key_clear_pair in self.clear_values_column_pairs.all():
                column_name = key_clear_pair.column
                clear_out_value = key_clear_pair.value
                try:
                    if row[column_name] == clear_out_value:
                        include_row = False
                        break
                except KeyError:
                    continue
            if include_row:
                cleaned_rows.append(row)

        return cleaned_rows


class UtilityBillRule(models.Model):
    """
    Config (one row per property+utility) that ties a utility account to a
    ledger account. Holds both how to find the bill email (from_address +
    subject) and how to book the matching bank transaction
    (account_number resolves the property; transaction_description_match,
    account, entity, transaction_type drive the match).
    """

    # How to find the email
    from_address = models.CharField(max_length=200)
    subject = models.CharField(max_length=200)

    # How to resolve the property
    account_number = models.CharField(max_length=100)
    address_hint = models.CharField(max_length=200, blank=True)

    # How to match and book the bank transaction
    transaction_description_match = models.CharField(max_length=200)
    account = models.ForeignKey("Account", on_delete=models.PROTECT)
    entity = models.ForeignKey(
        "Entity",
        related_name="utility_bill_rules",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    transaction_type = models.CharField(
        max_length=25,
        choices=Transaction.TransactionType.choices,
        default=Transaction.TransactionType.PURCHASE,
    )

    def __str__(self):
        return f"{self.from_address} #{self.account_number} -> {self.account}"


class UtilityBill(models.Model):
    """Runtime record: one row per utility-bill email ingested from Gmail."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PARSED = "parsed", _("Parsed")
        UNRESOLVED = "unresolved", _("Unresolved")
        MATCHED = "matched", _("Matched")
        FAILED = "failed", _("Failed")

    # Dedupe guard (Gmail message ID today; source-neutral name on purpose)
    source_message_id = models.CharField(max_length=200, unique=True)

    # Raw email
    from_address = models.CharField(max_length=200, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    raw_text = models.TextField(blank=True)
    received_at = models.DateTimeField(null=True, blank=True)

    # Parsed values
    vendor = models.CharField(max_length=200, blank=True)
    account_number = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(
        decimal_places=2, max_digits=12, null=True, blank=True
    )
    service_address = models.CharField(max_length=200, blank=True)
    bill_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    payment_date = models.DateField(null=True, blank=True)

    # Resolution
    rule = models.ForeignKey(
        "UtilityBillRule", on_delete=models.SET_NULL, null=True, blank=True
    )
    account = models.ForeignKey(
        "Account",
        related_name="utility_bills",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    entity = models.ForeignKey(
        "Entity",
        related_name="utility_bills",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    # Link to the bank transaction it tagged
    matched_transaction = models.ForeignKey(
        "Transaction",
        related_name="utility_bills",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=25, choices=Status.choices, default=Status.PENDING
    )
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.vendor or self.from_address} ${self.amount} [{self.status}]"

    @property
    def short_error(self) -> str:
        """A compact, human-friendly label for the stored error_message."""
        return short_error_label(self.error_message)


class Loan(models.Model):
    """
    A loan with a generated amortization schedule. Each loan books its principal
    against a dedicated LIABILITY account and its interest against a dedicated
    EXPENSE account, so an imported payment can be split automatically.

    The schedule (LoanPayment rows) is computed from the terms but every row's
    principal/interest is editable to match the lender exactly. Off-schedule
    principal-only payments and early payoffs are recorded as their own rows and
    the remaining schedule is re-amortized.
    """

    name = models.CharField(max_length=200, unique=True)
    original_amount = models.DecimalField(decimal_places=2, max_digits=12)
    # Stored as a decimal fraction, e.g. 0.0650 for 6.5% APR.
    annual_interest_rate = models.DecimalField(decimal_places=4, max_digits=6)
    term_months = models.PositiveSmallIntegerField()
    start_date = models.DateField()  # date of the first scheduled payment
    # Computed from the terms when left blank.
    payment_amount = models.DecimalField(
        decimal_places=2, max_digits=12, null=True, blank=True
    )

    principal_account = models.ForeignKey(
        "Account", related_name="loans_principal", on_delete=models.PROTECT
    )
    interest_account = models.ForeignKey(
        "Account", related_name="loans_interest", on_delete=models.PROTECT
    )
    # Bank account payments are drawn from; scopes which transactions can match.
    payment_account = models.ForeignKey(
        "Account",
        related_name="loans_payment",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    # Substring matched against a transaction's description (like a bill rule).
    description_match = models.CharField(max_length=200, blank=True)
    date_window_days = models.PositiveSmallIntegerField(default=7)

    entity = models.ForeignKey(
        "Entity",
        related_name="loans",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    is_closed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name} ${self.original_amount}"

    @staticmethod
    def _round(value, places=2):
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _add_months(base, count):
        """base shifted forward by ``count`` whole months, clamping the day to
        the target month's length (so the 31st becomes the 28th/30th)."""
        month_index = base.month - 1 + count
        year = base.year + month_index // 12
        month = month_index % 12 + 1
        day = min(base.day, calendar.monthrange(year, month)[1])
        return datetime.date(year, month, day)

    def _month_offset(self, date):
        """Whole months from the loan's start_date to ``date`` (a payment's
        position in the monthly cadence; the first payment is offset 0)."""
        return (date.year - self.start_date.year) * 12 + (
            date.month - self.start_date.month
        )

    def compute_monthly_payment(self):
        """Standard fully-amortizing payment: P*r/(1-(1+r)^-n)."""
        principal = self.original_amount
        periods = self.term_months
        rate = self.annual_interest_rate / 12
        if rate == 0:
            return self._round(principal / periods)
        factor = (1 + rate) ** periods
        payment = principal * rate * factor / (factor - 1)
        return self._round(payment)

    def _fixed_rows(self):
        """Rows that fix the balance: actual (paid) payments and balance anchors,
        in chronological order."""
        return list(
            self.payments.filter(
                Q(transaction__isnull=False) | Q(balance_override__isnull=False)
            ).order_by("date", "sequence")
        )

    def _running_balance(self, rows, persist=False):
        """Rolls the balance forward through ``rows``: a balance anchor resets
        the running balance, otherwise each payment's principal reduces it.
        When ``persist`` is set, writes each row's resulting remaining_balance."""
        balance = self.original_amount
        for row in rows:
            if row.balance_override is not None:
                balance = self._round(row.balance_override)
            else:
                balance = self._round(balance - row.principal_amount)
            if persist:
                row.remaining_balance = balance
        return balance

    def remaining_balance(self):
        """Outstanding principal, honoring any balance-anchor reset."""
        return self._round(self._running_balance(self._fixed_rows()))

    def _build_schedule(self, balance, first_date, start_sequence, payment):
        rate = self.annual_interest_rate / 12
        rows = []
        sequence = start_sequence
        date = first_date
        max_rows = self.term_months + 2  # guard against rounding loops
        while balance > 0 and len(rows) < max_rows:
            interest = self._round(balance * rate)
            principal = payment - interest
            if principal >= balance:
                # Final payment absorbs the remaining balance and rounding.
                principal = balance
                row_payment = self._round(principal + interest)
            else:
                row_payment = payment
            balance = self._round(balance - principal)
            rows.append(
                LoanPayment(
                    loan=self,
                    sequence=sequence,
                    date=date,
                    payment_amount=row_payment,
                    principal_amount=principal,
                    interest_amount=interest,
                    remaining_balance=balance,
                    kind=LoanPayment.Kind.SCHEDULED,
                )
            )
            sequence += 1
            date = self._add_months(date, 1)
        LoanPayment.objects.bulk_create(rows)

    def generate_schedule(self):
        """Rebuild the forecast rows, preserving fixed rows (paid payments and
        balance anchors).

        Used at creation (no fixed rows -> full schedule) and to re-amortize
        after an off-schedule/edited payment or a balance reset: the running
        balance is rolled forward through the fixed rows (honoring any anchor),
        then the remaining periods are forecast from the current balance.
        """
        # Drop only the disposable forecast rows — keep paid payments and any
        # balance-anchored row.
        self.payments.filter(
            transaction__isnull=True, balance_override__isnull=True
        ).delete()
        payment = self.payment_amount or self.compute_monthly_payment()
        if self.payment_amount != payment:
            self.payment_amount = payment
            self.save(update_fields=["payment_amount"])

        fixed = self._fixed_rows()
        balance = self._running_balance(fixed, persist=True)
        if fixed:
            LoanPayment.objects.bulk_update(fixed, ["remaining_balance"])

        if balance <= 0 or self.is_closed:
            return

        # Continue the forecast on the original monthly cadence, picking up one
        # slot after the latest *scheduled* fixed row's calendar position. Using
        # the position (not a raw count) keeps the dates right even when a fixed
        # row sits later in the schedule (e.g. a balance anchored mid-loan).
        # Off-schedule (principal-only/payoff) payments reduce the balance but
        # don't consume a calendar slot, so they never shift the due dates.
        scheduled_offsets = [
            self._month_offset(p.date)
            for p in fixed
            if p.kind == LoanPayment.Kind.SCHEDULED
        ]
        consumed = (max(scheduled_offsets) + 1) if scheduled_offsets else 0
        first_date = self._add_months(self.start_date, consumed)
        start_sequence = max((p.sequence for p in fixed), default=0) + 1
        self._build_schedule(balance, first_date, start_sequence, payment)


class LoanPayment(models.Model):
    """One amortization-schedule row (or recorded off-schedule payment)."""

    class Kind(models.TextChoices):
        SCHEDULED = "scheduled", _("Scheduled")
        PRINCIPAL_ONLY = "principal_only", _("Principal-only")
        PAYOFF = "payoff", _("Payoff")

    loan = models.ForeignKey("Loan", related_name="payments", on_delete=models.CASCADE)
    sequence = models.PositiveSmallIntegerField()
    date = models.DateField()
    payment_amount = models.DecimalField(decimal_places=2, max_digits=12)
    principal_amount = models.DecimalField(decimal_places=2, max_digits=12)
    interest_amount = models.DecimalField(decimal_places=2, max_digits=12, default=0)
    remaining_balance = models.DecimalField(decimal_places=2, max_digits=12)
    # When set, the outstanding principal is forced to this value as of this row
    # (a user "reset" of the balance) and the forward schedule amortizes from it,
    # ignoring any unreliable computed history before it.
    balance_override = models.DecimalField(
        decimal_places=2, max_digits=12, null=True, blank=True
    )
    kind = models.CharField(
        max_length=20, choices=Kind.choices, default=Kind.SCHEDULED
    )
    transaction = models.OneToOneField(
        "Transaction",
        related_name="loan_payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["loan", "sequence"]

    @property
    def is_anchored(self):
        """True when the outstanding balance has been manually reset here."""
        return self.balance_override is not None

    def __str__(self):
        return f"{self.loan.name} #{self.sequence} {self.date} ${self.payment_amount}"


class RecharacterizeChange(models.Model):
    """A single applied recharacterize operation, recorded so it can be reverted.

    One row per Apply. Together with its RecharacterizeChangeItem rows (the
    per-item before-state) it captures everything needed to undo the bulk
    ``.update()`` the apply ran. Bounded over time by a recent-N retention cap
    (see recharacterize_services.RECHARACTERIZE_HISTORY_LIMIT).
    """

    created_at = models.DateTimeField(auto_now_add=True)
    action_kind = models.CharField(max_length=20)
    action_summary = models.CharField(max_length=255)
    criteria_summary = models.TextField(blank=True)
    updated_count = models.PositiveIntegerField(default=0)
    # The value the action set, kept so revert can tell items this change still
    # owns from items a later operation changed again (a conflict it must skip).
    new_account = models.ForeignKey(
        "Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    new_entity = models.ForeignKey(
        "Entity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    is_reverted = models.BooleanField(default=False)
    reverted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action_summary} ({self.updated_count})"


class RecharacterizeChangeItem(models.Model):
    """The before-state of one JournalEntryItem touched by a RecharacterizeChange.

    Stores both prior values even though one action mutates one field; revert
    restores only the field matching the change's ``action_kind``. The snapshot
    FKs are SET_NULL so history never blocks deleting an account/entity, and the
    item FK is SET_NULL so the row survives (and revert can report it) if the
    item is later deleted.
    """

    change = models.ForeignKey(
        "RecharacterizeChange", related_name="items", on_delete=models.CASCADE
    )
    journal_entry_item = models.ForeignKey(
        "JournalEntryItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    prior_account = models.ForeignKey(
        "Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    prior_entity = models.ForeignKey(
        "Entity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
