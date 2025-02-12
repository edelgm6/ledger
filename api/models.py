import datetime
import math
import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from textractor.entities.document import Document

from api.aws_services import (
    clean_and_convert_string_to_decimal,
    clean_string,
    convert_table_to_cleaned_dataframe,
    create_textract_job,
    get_textract_results,
)


class Entity(models.Model):
    name = models.CharField(max_length=200, unique=True)
    is_closed = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "entities"

    def __str__(self):
        return self.name


class S3File(models.Model):
    prefill = models.ForeignKey("Prefill", on_delete=models.PROTECT)
    url = models.URLField(max_length=200, unique=True)
    user_filename = models.CharField(max_length=200)
    s3_filename = models.CharField(max_length=200)
    textract_job_id = models.CharField(max_length=200)
    analysis_complete = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return self.prefill.name + " " + self.s3_filename

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
                        )
                    )
            PaystubValue.objects.bulk_create(paystub_values)

    def _extract_data(self):

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
                        data[kv.page_id][identifier][
                            "entry_type"
                        ] = keyword_search.journal_entry_item_type
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
                    data[table.page_id][identifier][
                        "entry_type"
                    ] = table_search.journal_entry_item_type

        return data


class Amortization(models.Model):
    accrued_journal_entry_item = models.OneToOneField(
        "JournalEntryItem", on_delete=models.CASCADE, related_name="amortization"
    )
    amount = models.DecimalField(decimal_places=2, max_digits=12)
    periods = models.PositiveSmallIntegerField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)
    description = models.CharField(max_length=200)
    suggested_account = models.ForeignKey("Account", on_delete=models.PROTECT)

    def __str__(self):
        return self.description + " $" + str(self.amount)

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
        remaining_balance = self.amount + total_amortized

        related_transactions_count = len(related_transactions)
        remaining_periods = self.periods - related_transactions_count

        max_date = related_transactions[0].date if related_transactions else ""

        return remaining_balance, remaining_periods, max_date

    def amortize(self, date):
        starting_amortization_count = len(self.get_related_transactions())

        if self.periods - starting_amortization_count == 0 or self.is_closed:
            raise ValidationError("Cannot further amortize")
        elif self.periods - starting_amortization_count == 1:
            amortization_amount, _ = self.get_remaining_balance_and_periods()
            is_final_amortization = True
        else:
            amortization_amount = self._round_down(self.amount / self.periods)
            is_final_amortization = False

        prepaid_account = Account.objects.get(
            special_type=Account.SpecialType.PREPAID_EXPENSES
        )

        transaction = Transaction.objects.create(
            date=date,
            account=prepaid_account,
            amount=amortization_amount * -1,
            description=(
                self.description
                + " amortization #"
                + str(len(self.get_related_transactions()) + 1)
            ),
            suggested_account=self.suggested_account,
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
        )

        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=account_entry_type,
            amount=abs(delta),
            account=self.account,
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
    amount = models.DecimalField(decimal_places=2, max_digits=12)
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

    type = models.CharField(max_length=25, choices=Type.choices)
    transaction = models.OneToOneField("Transaction", on_delete=models.PROTECT)
    date = models.DateField()
    amount = models.DecimalField(decimal_places=2, max_digits=12)

    class Meta:
        unique_together = [["type", "date"]]

    def __str__(self):
        return str(self.date) + " " + self.type

    def _get_tax_accounts(self):
        tax_accounts = {
            self.Type.STATE: {
                "expense": Account.objects.get(
                    special_type=Account.SpecialType.STATE_TAXES
                ),
                "liability": Account.objects.get(
                    special_type=Account.SpecialType.STATE_TAXES_PAYABLE
                ),
                "description": "State Income Tax",
            },
            self.Type.FEDERAL: {
                "expense": Account.objects.get(
                    special_type=Account.SpecialType.FEDERAL_TAXES
                ),
                "liability": Account.objects.get(
                    special_type=Account.SpecialType.FEDERAL_TAXES_PAYABLE
                ),
                "description": "Federal Income Tax",
            },
            self.Type.PROPERTY: {
                "expense": Account.objects.get(
                    special_type=Account.SpecialType.PROPERTY_TAXES
                ),
                "liability": Account.objects.get(
                    special_type=Account.SpecialType.PROPERTY_TAXES_PAYABLE
                ),
                "description": "Property Tax",
            },
        }
        return tax_accounts[self.type]

    def save(self, *args, **kwargs):
        accounts = self._get_tax_accounts()

        try:
            transaction = self.transaction
            transaction.amount = self.amount
            transaction.save()
        except Transaction.DoesNotExist:
            transaction = Transaction.objects.create(
                date=self.date,
                account=accounts["expense"],
                amount=self.amount,
                description=str(self.date) + " " + accounts["description"],
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

        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=self.transaction.amount,
            account=accounts["expense"],
        )
        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=self.transaction.amount,
            account=accounts["liability"],
        )

        # Update the Reconciliation per the new tax amount
        liability_account = accounts["liability"]
        liability_balance = liability_account.get_balance(self.date)
        try:
            reconciliation = Reconciliation.objects.get(
                date=self.date, account=accounts["liability"]
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
        WALLET = "wallet", _("Wallet")
        PREPAID_EXPENSES = "prepaid_expenses", _("Prepaid Expenses")

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
        ACCOUNTS_PAYABLE = "accounts_payable", _("Accounts Payable")
        # Asset types
        CASH = "cash", _("Cash")
        ACCOUNTS_RECEIVABLE = "accounts_receivable", _("Accounts Receivable")
        PREPAID_EXPENSES = "prepaid_expenses", _("Prepaid Expenses")
        SECURITIES_UNRESTRICTED = (
            "securities_unrestricted",
            _("Securities-Unrestricted"),
        )
        SECURITIES_RETIREMENT = ("securities_retirement", _("Securities-Retirement"))
        REAL_ESTATE = "real_estate", _("Real Estate")
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
        PURCHASES = "purchases", _("Purchases")
        TAX = "tax", _("Tax")
        INTEREST = "interest", _("Interest Expense")

    # TODO: Add a test that makes sure every type/subtype is represented here
    SUBTYPE_TO_TYPE_MAP = {
        Type.LIABILITY: [
            SubType.SHORT_TERM_DEBT,
            SubType.ACCOUNTS_PAYABLE,
            SubType.TAXES_PAYABLE,
            SubType.LONG_TERM_DEBT,
        ],
        Type.ASSET: [
            SubType.CASH,
            SubType.ACCOUNTS_RECEIVABLE,
            SubType.PREPAID_EXPENSES,
            SubType.SECURITIES_UNRESTRICTED,
            SubType.SECURITIES_RETIREMENT,
            SubType.REAL_ESTATE,
        ],
        Type.EQUITY: [SubType.RETAINED_EARNINGS],
        Type.INCOME: [
            SubType.SALARY,
            SubType.DIVIDENDS_AND_INTEREST,
            SubType.REALIZED_INVESTMENT_GAINS,
            SubType.OTHER_INCOME,
            SubType.UNREALIZED_INVESTMENT_GAINS,
        ],
        Type.EXPENSE: [SubType.PURCHASES, SubType.INTEREST, SubType.TAX],
    }

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
        max_length=30, choices=SpecialType.choices, null=True, blank=True, unique=True
    )
    is_closed = models.BooleanField(default=False)
    entity = models.ForeignKey(
        "Entity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounts",
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

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


class JournalEntryItem(models.Model):

    class JournalEntryType(models.TextChoices):
        DEBIT = "debit", _("Debit")
        CREDIT = "credit", _("Credit")

    journal_entry = models.ForeignKey(
        "JournalEntry", related_name="journal_entry_items", on_delete=models.CASCADE
    )
    type = models.CharField(max_length=6, choices=JournalEntryType.choices)
    amount = models.DecimalField(decimal_places=2, max_digits=12)
    account = models.ForeignKey("Account", on_delete=models.PROTECT)
    entity = models.ForeignKey(
        "Entity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal_entry_items",
    )

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

    def __str__(self):
        return self.name


class PrefillItem(models.Model):
    prefill = models.ForeignKey("Prefill", on_delete=models.CASCADE)
    account = models.ForeignKey("Account", on_delete=models.CASCADE)
    journal_entry_item_type = models.CharField(
        max_length=25, choices=JournalEntryItem.JournalEntryType.choices
    )
    order = models.PositiveSmallIntegerField()
    entity = models.ForeignKey(
        "Entity",
        related_name="prefill_item",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )


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
        CSVColumnValuePair, null=True, blank=True
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
            if row == {} or self._get_coalesced_amount(row) == 0:
                break

            # Set defaults
            transaction = Transaction(
                date=self._get_formatted_date(row[self.date]),
                account=account,
                amount=self._get_coalesced_amount(row),
                description=row[self.description],
                category=row[self.category],
                suggested_account=None,  # Default value
                prefill=None,  # Default value
                type=Transaction.TransactionType.PURCHASE,  # Default type
            )
            transactions_list.append(transaction)

        Transaction.apply_autotags(transactions_list)
        Transaction.objects.bulk_create(transactions_list)

        return len(transactions_list)

    def _get_formatted_date(self, date_string):
        # Parse the original date using the input format
        original_date = datetime.datetime.strptime(date_string, self.date_format)

        # Format the date to the desired output format
        formatted_date = original_date.strftime("%Y-%m-%d")

        return formatted_date

    def _get_coalesced_amount(self, row):
        if row[self.inflow]:
            return row[self.inflow]
        else:
            return row[self.outflow]

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
