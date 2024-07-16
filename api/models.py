import math
import datetime
import boto3
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from decimal import Decimal
from textractor.entities.document import Document

class Paystub(models.Model):
    document = models.ForeignKey('S3File', on_delete=models.CASCADE)
    page_id = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    journal_entry = models.OneToOneField('Prefill', null=True, blank=True, on_delete=models.SET_NULL)


class PaystubValue(models.Model):
    paystub = models.ForeignKey('Paystub', on_delete=models.CASCADE)
    account = models.ForeignKey('Account', on_delete=models.PROTECT)
    amount = models.DecimalField(decimal_places=2, max_digits=12)


class DocSearch(models.Model):
    prefill = models.ForeignKey('Prefill', on_delete=models.PROTECT)
    keyword = models.CharField(max_length=200, null=True, blank=True)
    table_name = models.CharField(max_length=200, null=True, blank=True)
    row = models.CharField(max_length=200, null=True, blank=True)
    column = models.CharField(max_length=200, null=True, blank=True)
    account = models.ForeignKey('Account', null=True, blank=True, on_delete=models.SET_NULL)
    
    STRING_CHOICES = [
        ('Company', 'Company'),
        ('Begin Period', 'Begin Period'),
        ('End Period', 'End Period'),
    ]
    selection = models.CharField(max_length=20, choices=STRING_CHOICES, null=True, blank=True)

    def clean(self):
        super().clean()

        # Check the existing conditions
        if not self.keyword and (self.row is None or self.column is None):
            raise ValidationError("Either 'keyword' must be provided, or both 'row' and 'column' must be provided.")
        
        # Ensure either account or selection is set
        if not self.account and not self.selection:
            raise ValidationError("Either 'account' must be provided, or 'selection' must be one of the specified choices.")
        
        if self.account and self.selection:
            raise ValidationError("Both 'account' and 'selection' cannot be set at the same time.")
        
    def get_selection_or_account(self):
        if self.selection:
            return self.selection
        return self.account


class S3File(models.Model):
    prefill = models.OneToOneField('Prefill', on_delete=models.PROTECT)
    url = models.URLField(max_length=200, unique=True)
    user_filename = models.CharField(max_length=200)
    s3_filename = models.CharField(max_length=200)
    textract_job_id = models.CharField(max_length=200, null=True, blank=True)

    def process_document_with_textract(self):
        # Boto3 client for Textract
        client = boto3.client(
            'textract',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION_NAME
        )

        # Process file
        response = client.start_document_analysis(
            DocumentLocation={
                'S3Object': {
                    'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                    'Name': self.s3_filename
                }
            },
            FeatureTypes=[
                'FORMS','TABLES'
            ]
        )
        job_id = response.get('JobId')
        self.textract_job_id = job_id
        self.save()
        return job_id
        
    # Get all responses, paginated
    def get_textract_results(self):
        client = boto3.client(
            'textract',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION_NAME
        )

        responses = []
        next_token = None
        while True:
            if next_token:
                response = client.get_document_analysis(JobId=self.textract_job_id, NextToken=next_token)
            else:
                response = client.get_document_analysis(JobId=self.textract_job_id)
            
            responses.append(response)
            next_token = response.get('NextToken')
            if not next_token:
                break
        return responses

    # Combine responses
    @staticmethod
    def combine_responses(responses):
        combined_response = {
            "DocumentMetadata": {
                "Pages": ""
            },
            "Blocks": []
        }

        for response in responses:
            combined_response["DocumentMetadata"]["Pages"] = response["DocumentMetadata"]["Pages"]
            combined_response["Blocks"].extend(response["Blocks"])

        return combined_response
    
    @staticmethod
    def clean_string(input_string):
        if input_string is None:
            return None
        # Remove commas
        cleaned_string = input_string.replace(',', '')
        
        # Remove starting/trailing whitespace and ensure only one space between words
        cleaned_string = ' '.join(cleaned_string.split())
        
        return cleaned_string
    
    @staticmethod
    def clean_and_convert_string_to_decimal(input_string):
        cleaned_string = S3File.clean_string(input_string)
        cleaned_string = cleaned_string.replace(',', '').replace('$', '')
        print(cleaned_string)
        return Decimal(cleaned_string).quantize(Decimal('0.00'))

    @staticmethod
    def extract_data(textract_job_response):
        
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
        keyword_searches = DocSearch.objects.filter(keyword__isnull=False)

        for kv in key_value_pairs:
            key = S3File.clean_string(kv.key.text)
            for keyword_search in keyword_searches:
                if key == keyword_search.keyword:
                    identifier = keyword_search.get_selection_or_account()
                    data[kv.page_id][identifier] = S3File.clean_string(kv.value.text)

        # Step 3: Grab table data from tables
        table_searches = DocSearch.objects.filter(keyword__isnull=True)
        for table in document.tables:
            for table_search in table_searches:
                table_title = table.title if table.title is None else table.title.text
                both_table_names_none_condition = table_search.table_name is None and table_title is None
                table_names_equal_condition = table_search.table_name == S3File.clean_string(table_title)

                if not (both_table_names_none_condition or table_names_equal_condition):
                    continue

                pandas_table = S3File.convert_table_to_cleaned_dataframe(table)
                try:
                    value = pandas_table.loc[table_search.row, table_search.column]
                except KeyError:
                    continue

                value = S3File.clean_and_convert_string_to_decimal(value)
                identifier = table_search.get_selection_or_account()
                if identifier in data[table.page_id]:
                    data[table.page_id][identifier] += value
                else:
                    data[table.page_id][identifier] = value

        print(data)
        return data

    @staticmethod
    def convert_table_to_cleaned_dataframe(table):
        no_titles_table = table.strip_headers(column_headers=False, in_table_title=True, section_titles=True)
        
        pandas_table = no_titles_table.to_pandas()

        # Set the first row as the header
        pandas_table.columns = pandas_table.iloc[0]
        pandas_table = pandas_table[1:]

        # Set the first column as the index
        pandas_table.set_index(pandas_table.columns[0], inplace=True)

        # Strip whitespace from column names and index
        pandas_table.columns = pandas_table.columns.str.strip()
        pandas_table.index = pandas_table.index.str.strip()

        return pandas_table

class Amortization(models.Model):
    accrued_transaction = models.OneToOneField(
        'Transaction',
        on_delete=models.CASCADE,
        related_name='accrued_amortizations'
    )
    amount = models.DecimalField(decimal_places=2, max_digits=12)
    periods = models.PositiveSmallIntegerField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)
    description = models.CharField(max_length=200)
    suggested_account = models.ForeignKey('Account', on_delete=models.PROTECT)

    @staticmethod
    def _round_down(n, decimals=2):
        multiplier = 10 ** decimals
        return math.floor(n * multiplier) / multiplier

    def get_related_transactions(self):
        return self.transactions.all().order_by('date')

    def get_remaining_periods(self):
        related_transactions_count = len(self.get_related_transactions())
        return self.periods - related_transactions_count

    def get_remaining_balance(self):
        related_transactions = self.get_related_transactions()
        total_amortized = sum(
            [transaction.amount for transaction in related_transactions]
        )
        return self.amount + total_amortized

    def amortize(self, date):
        starting_amortization_count = len(self.get_related_transactions())

        if self.periods - starting_amortization_count == 0 or self.is_closed:
            raise ValidationError('Cannot further amortize')
        elif self.periods - starting_amortization_count == 1:
            amortization_amount = self.get_remaining_balance()
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
                self.description +
                ' amorization #' +
                str(len(self.get_related_transactions()) + 1)
            ),
            suggested_account=self.suggested_account,
            type=Transaction.TransactionType.PURCHASE,
            amortization=self
        )

        if is_final_amortization:
            self.is_closed = True
            self.save()
        return transaction


class Reconciliation(models.Model):
    account = models.ForeignKey('Account', on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(
        decimal_places=2,
        max_digits=12,
        null=True,
        blank=True
    )
    transaction = models.OneToOneField(
        'Transaction',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    class Meta:
        unique_together = [['account', 'date']]

    def __str__(self):
        return str(self.date) + ' ' + self.account.name

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
                    str(self.date) +
                    ' Plug gain/loss for ' +
                    self.account.name
                )
            )
            self.transaction = transaction
            self.save()

        try:
            journal_entry = transaction.journal_entry
        except JournalEntry.DoesNotExist:
            journal_entry = JournalEntry.objects.create(
                date=self.date,
                description=transaction.description,
                transaction=transaction
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
            account=GAIN_LOSS_ACCOUNT
        )

        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=account_entry_type,
            amount=abs(delta),
            account=self.account
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
        related_accounts=None
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
        return queryset.order_by('date', 'account', 'pk')


class TransactionManager(models.Manager):
    def get_queryset(self):
        return TransactionQuerySet(self.model, using=self._db)

    def filter_for_table(self, *args, **kwargs):
        return self.get_queryset().filter_for_table(*args, **kwargs)


class Transaction(models.Model):

    class TransactionType(models.TextChoices):
        INCOME = 'income', _('Income')
        PURCHASE = 'purchase', _('Purchase')
        PAYMENT = 'payment', _('Payment')
        TRANSFER = 'transfer', _('Transfer')

    date = models.DateField()
    account = models.ForeignKey('Account', on_delete=models.PROTECT)
    amount = models.DecimalField(decimal_places=2, max_digits=12)
    description = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=200, blank=True)
    is_closed = models.BooleanField(default=False)
    date_closed = models.DateField(null=True, blank=True)
    suggested_account = models.ForeignKey(
        'Account',
        related_name='suggested_account',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    type = models.CharField(max_length=25, choices=TransactionType.choices)
    linked_transaction = models.OneToOneField(
        'Transaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    amortization = models.ForeignKey(
        'Amortization',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='transactions'
    )
    prefill = models.ForeignKey(
        'Prefill',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    objects = TransactionManager()

    class Meta:
        indexes = [
            models.Index(fields=['date'], name='date_idx'),
            models.Index(fields=['account'], name='account_idx'),
            models.Index(fields=['type'], name='type_idx'),
            models.Index(fields=['is_closed'], name='is_closed_idx'),
            models.Index(fields=['linked_transaction'], name='linked_transaction_idx'),
        ]

    def __str__(self):
        return (
            str(self.date) + ' ' +
            self.account.name + ' ' +
            self.description + ' $' +
            str(self.amount)
        )

    def close(self, date=datetime.date.today()):
        self.is_closed = True
        self.date_closed = date
        self.save()

    def create_link(self, transaction):
        self.linked_transaction = transaction
        self.suggested_account = transaction.account
        self.save()
        transaction.close()


class TaxCharge(models.Model):
    class Type(models.TextChoices):
        PROPERTY = 'property', _('Property')
        FEDERAL = 'federal', _('Federal')
        STATE = 'state', _('State')

    type = models.CharField(max_length=25, choices=Type.choices)
    transaction = models.OneToOneField('Transaction', on_delete=models.PROTECT)
    date = models.DateField()
    amount = models.DecimalField(decimal_places=2, max_digits=12)

    class Meta:
        unique_together = [['type', 'date']]

    def __str__(self):
        return str(self.date) + ' ' + self.type

    def _get_tax_accounts(self):
        tax_accounts = {
            self.Type.STATE: {
                'expense': Account.objects.get(
                    special_type=Account.SpecialType.STATE_TAXES
                ),
                'liability': Account.objects.get(
                    special_type=Account.SpecialType.STATE_TAXES_PAYABLE
                ),
                'description': 'State Income Tax'
            },
            self.Type.FEDERAL: {
                'expense': Account.objects.get(
                    special_type=Account.SpecialType.FEDERAL_TAXES
                ),
                'liability': Account.objects.get(
                    special_type=Account.SpecialType.FEDERAL_TAXES_PAYABLE
                ),
                'description': 'Federal Income Tax'

            },
            self.Type.PROPERTY: {
                'expense': Account.objects.get(
                    special_type=Account.SpecialType.PROPERTY_TAXES
                ),
                'liability': Account.objects.get(
                    special_type=Account.SpecialType.PROPERTY_TAXES_PAYABLE
                ),
                'description': 'Property Tax'
            }
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
                account=accounts['expense'],
                amount=self.amount,
                description=str(self.date) + ' ' + accounts['description'],
                is_closed=True,
                date_closed=datetime.date.today(),
                type=Transaction.TransactionType.PURCHASE
            )
            self.transaction = transaction

        try:
            journal_entry = self.transaction.journal_entry
        except JournalEntry.DoesNotExist:
            journal_entry = JournalEntry.objects.create(
                date=self.date,
                transaction=self.transaction
            )
        journal_entry.delete_journal_entry_items()

        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=self.transaction.amount,
            account=accounts['expense']
        )
        JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=self.transaction.amount,
            account=accounts['liability']
        )

        # Update the Reconciliation per the new tax amount
        liability_account = accounts['liability']
        liability_balance = liability_account.get_balance(self.date)
        try:
            reconciliation = Reconciliation.objects.get(
                date=self.date,
                account=accounts['liability']
            )
            reconciliation.amount = liability_balance
            reconciliation.save()
        except Reconciliation.DoesNotExist:
            pass

        super().save(*args, **kwargs)


class Account(models.Model):

    class SpecialType(models.TextChoices):
        UNREALIZED_GAINS_AND_LOSSES = (
            'unrealized_gains_and_losses', _('Unrealized Gains and Losses')
        )
        STATE_TAXES_PAYABLE = 'state_taxes_payable', _('State Taxes Payable')
        FEDERAL_TAXES_PAYABLE = (
            'federal_taxes_payable', _('Federal Taxes Payable')
        )
        PROPERTY_TAXES_PAYABLE = (
            'property_taxes_payable', _('Property Taxes Payable')
        )
        STATE_TAXES = 'state_taxes', _('State Taxes')
        FEDERAL_TAXES = 'federal_taxes', _('Federal Taxes')
        PROPERTY_TAXES = 'property_taxes', _('Property Taxes')
        WALLET = 'wallet', _('Wallet')
        PREPAID_EXPENSES = 'prepaid_expenses', _('Prepaid Expenses')

    class Type(models.TextChoices):
        ASSET = 'asset', _('Asset')
        LIABILITY = 'liability', _('Liability')
        INCOME = 'income', _('Income')
        EXPENSE = 'expense', _('Expense')
        EQUITY = 'equity', _('Equity')

    class SubType(models.TextChoices):
        # Liability types
        SHORT_TERM_DEBT = 'short_term_debt', _('Short-term Debt')
        TAXES_PAYABLE = 'taxes_payable', _('Taxes Payable')
        LONG_TERM_DEBT = 'long_term_debt', _('Long-term Debt')
        # Asset types
        CASH = 'cash', _('Cash')
        ACCOUNTS_RECEIVABLE = 'accounts_receivable', _('Accounts Receivable')
        SECURITIES_UNRESTRICTED = (
            'securities_unrestricted', _('Securities-Unrestricted')
        )
        SECURITIES_RETIREMENT = (
            'securities_retirement', _('Securities-Retirement')
        )
        REAL_ESTATE = 'real_estate', _('Real Estate')
        # Equity types
        RETAINED_EARNINGS = 'retained_earnings', _('Retained Earnings')
        # Income types
        SALARY = 'salary', _('Salary')
        DIVIDENDS_AND_INTEREST = (
            'dividends_and_interest', _('Dividends & Interest')
        )
        REALIZED_INVESTMENT_GAINS = (
            'realized_investment_gains', _('Realized Investment Gains')
        )
        OTHER_INCOME = 'other_income', _('Other Income')
        UNREALIZED_INVESTMENT_GAINS = (
            'unrealized_investment_gains', _('Unrealized Investment Gains')
        )
        # Expense Types
        PURCHASES = 'purchases', _('Purchases')
        TAX = 'tax', _('Tax')
        INTEREST = 'interest', _('Interest Expense')

    # TODO: Add a test that makes sure every type/subtype is represented here
    SUBTYPE_TO_TYPE_MAP = {
        Type.LIABILITY: [
            SubType.SHORT_TERM_DEBT,
            SubType.LONG_TERM_DEBT,
            SubType.TAXES_PAYABLE
        ],
        Type.ASSET: [
            SubType.CASH,
            SubType.REAL_ESTATE,
            SubType.SECURITIES_RETIREMENT,
            SubType.SECURITIES_UNRESTRICTED,
            SubType.ACCOUNTS_RECEIVABLE
        ],
        Type.EQUITY: [SubType.RETAINED_EARNINGS],
        Type.INCOME: [
            SubType.SALARY,
            SubType.DIVIDENDS_AND_INTEREST,
            SubType.REALIZED_INVESTMENT_GAINS,
            SubType.OTHER_INCOME,
            SubType.UNREALIZED_INVESTMENT_GAINS
        ],
        Type.EXPENSE: [SubType.PURCHASES, SubType.INTEREST, SubType.TAX]
    }

    name = models.CharField(max_length=200, unique=True)
    type = models.CharField(max_length=9, choices=Type.choices)
    sub_type = models.CharField(max_length=30, choices=SubType.choices)
    csv_profile = models.ForeignKey(
        'CSVProfile',
        related_name='accounts',
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    special_type = models.CharField(
        max_length=30,
        choices=SpecialType.choices,
        null=True,
        blank=True,
        unique=True
    )
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ('name',)

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
        INCOME_STATEMENT_ACCOUNT_TYPES = ['income', 'expense']

        journal_entry_items = JournalEntryItem.objects.filter(
            journal_entry__date__lte=end_date,
            account=self
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
            account_type=self.type,
            debits=debits,
            credits=credits
        )


class JournalEntry(models.Model):
    date = models.DateField()
    description = models.CharField(max_length=200, blank=True)
    transaction = models.OneToOneField(
        'Transaction',
        related_name='journal_entry',
        on_delete=models.CASCADE
    )

    def __str__(self):
        return str(self.pk) + ': ' + str(self.date) + ' ' + self.description

    def delete_journal_entry_items(self):
        journal_entry_items = JournalEntryItem.objects.filter(
            journal_entry=self
        )
        journal_entry_items.delete()


class JournalEntryItem(models.Model):

    class JournalEntryType(models.TextChoices):
        DEBIT = 'debit', _('Debit')
        CREDIT = 'credit', _('Credit')

    journal_entry = models.ForeignKey(
        'JournalEntry',
        related_name='journal_entry_items',
        on_delete=models.CASCADE
    )
    type = models.CharField(max_length=6, choices=JournalEntryType.choices)
    amount = models.DecimalField(decimal_places=2, max_digits=12)
    account = models.ForeignKey('Account', on_delete=models.PROTECT)

    class Meta:
        indexes = [
            models.Index(fields=['type'], name='jei_date_idx'),
            models.Index(fields=['account'], name='jei_account_idx'),
        ]

    def __str__(self):
        return (
            str(self.journal_entry.id) + ' ' + self.type +
            ' $' + str(self.amount)
        )


class AutoTag(models.Model):
    search_string = models.CharField(max_length=20)
    account = models.ForeignKey(
        'Account',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    transaction_type = models.CharField(
        max_length=25,
        choices=Transaction.TransactionType.choices,
        blank=True
    )
    prefill = models.ForeignKey(
        'Prefill',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    def __str__(self):
        return '"' + self.search_string + '": ' + str(self.account)


class Prefill(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class PrefillItem(models.Model):
    prefill = models.ForeignKey('Prefill', on_delete=models.CASCADE)
    account = models.ForeignKey('Account', on_delete=models.CASCADE)
    journal_entry_item_type = models.CharField(
        max_length=25,
        choices=JournalEntryItem.JournalEntryType.choices
    )
    order = models.PositiveSmallIntegerField()


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
        CSVColumnValuePair,
        null=True,
        blank=True
    )
    inflow = models.CharField(max_length=200)
    outflow = models.CharField(max_length=200)
    date_format = models.CharField(max_length=200, default='%Y-%m-%d')

    def __str__(self):
        return self.name

    def create_transactions_from_csv(self, csv, account):
        rows_cleaned_csv = self._clear_prepended_rows(csv)
        dict_based_csv = self._list_of_lists_to_list_of_dicts(rows_cleaned_csv)
        cleared_rows_csv = self._clear_extraneous_rows(dict_based_csv)

        transactions_list = []
        for row in cleared_rows_csv:
            if row == {}:
                continue

            # Set defaults
            transaction_type = Transaction.TransactionType.PURCHASE
            suggested_account = None
            prefill = None
            # Loop through AutoTags to find
            # the first match with the description
            for tag in AutoTag.objects.all():
                if tag.search_string.lower() in row[self.description].lower():
                    suggested_account = tag.account
                    prefill = tag.prefill
                    # Only override the transaction type
                    # if it's specified in the tag
                    tag_type = tag.transaction_type
                    transaction_type = (
                        tag_type if tag_type else transaction_type
                    )
                    break

            transactions_list.append(
                Transaction(
                    date=self._get_formatted_date(row[self.date]),
                    account=account,
                    amount=self._get_coalesced_amount(row),
                    description=row[self.description],
                    category=row[self.category],
                    suggested_account=suggested_account,
                    prefill=prefill,
                    type=transaction_type
                )
            )

        Transaction.objects.bulk_create(transactions_list)

        return len(transactions_list)

    def _get_formatted_date(self, date_string):
        # Parse the original date using the input format
        original_date = datetime.datetime.strptime(
            date_string,
            self.date_format
        )

        # Format the date to the desired output format
        formatted_date = original_date.strftime('%Y-%m-%d')

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
        list_of_dicts = [
            dict(zip(trimmed_headings, row)) for row in list_of_lists[1:]
        ]
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
