import datetime
from django.db import models
from django.utils.translation import gettext_lazy as _

class Reconciliation(models.Model):
    account = models.ForeignKey('Account',on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(decimal_places=2,max_digits=12,null=True,blank=True)
    transaction = models.OneToOneField('Transaction',on_delete=models.CASCADE,null=True,blank=True)

    class Meta:
        unique_together = [['account','date']]

    def __str__(self):
        return str(self.date) + ' ' + self.account.name

    def plug_investment_change(self):
        GAIN_LOSS_ACCOUNT = Account.objects.get(special_type=Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES)

        delta = self.amount - (self.account.get_balance(self.date) - (self.transaction.amount if self.transaction is not None else 0))

        if self.transaction:
            transaction = self.transaction
            transaction.amount = delta
            transaction.save()
        else:
            transaction = Transaction.objects.create(
                date=self.date,
                amount=delta,
                account=self.account,
                description=str(self.date) + ' Plug gain/loss for ' + self.account.name
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

        journal_entry_items = JournalEntryItem.objects.filter(journal_entry=journal_entry)
        journal_entry_items.delete()

        gain_loss_entry = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=gain_loss_entry_type,
            amount=abs(delta),
            account=GAIN_LOSS_ACCOUNT
        )

        account_entry = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=account_entry_type,
            amount=abs(delta),
            account=self.account
        )

        transaction.close(datetime.date.today())

        return journal_entry

class Transaction(models.Model):

    class TransactionType(models.TextChoices):
        INCOME = 'income', _('Income')
        PURCHASE = 'purchase', _('Purchase')
        PAYMENT = 'payment', _('Payment')
        TRANSFER = 'transfer', _('Transfer')

    date = models.DateField()
    account = models.ForeignKey('Account',on_delete=models.CASCADE)
    amount = models.DecimalField(decimal_places=2,max_digits=12)
    description = models.CharField(max_length=200,blank=True)
    category = models.CharField(max_length=200,blank=True)
    is_closed = models.BooleanField(default=False)
    date_closed = models.DateField(null=True,blank=True)
    suggested_account = models.ForeignKey('Account',related_name='suggested_account',on_delete=models.CASCADE,null=True,blank=True)
    type = models.CharField(max_length=25,choices=TransactionType.choices,blank=True)
    linked_transaction = models.OneToOneField('Transaction',on_delete=models.SET_NULL,null=True,blank=True)

    def __str__(self):
        return str(self.date) + ' ' + self.account.name + ' ' + self.description + ' $' + str(self.amount)

    def save(self, *args, **kwargs):
        suggested_account = None
        suggested_type = Transaction.TransactionType.PURCHASE
        auto_tags = AutoTag.objects.all()

        for tag in auto_tags:
            if tag.search_string in self.description.lower():
                suggested_account = tag.account
                if tag.transaction_type:
                    suggested_type = tag.transaction_type
                break

        self.suggested_account = suggested_account
        self.type = self.type or suggested_type
        super().save(*args, **kwargs)

    def close(self, date):
        self.is_closed = True
        self.date_closed = date
        self.save()

class TaxCharge(models.Model):
    class Type(models.TextChoices):
        PROPERTY = 'property', _('Property')
        FEDERAL = 'federal', _('Federal')
        STATE = 'state', _('State')

    type = models.CharField(max_length=25,choices=Type.choices)
    transaction = models.OneToOneField('Transaction',on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(decimal_places=2,max_digits=12)

    def __str__(self):
        return str(self.date) + ' ' + self.type

    def save(self, *args, **kwargs):
        tax_accounts = {
            self.Type.STATE: {
                'expense': Account.objects.get(special_type=Account.SpecialType.STATE_TAXES),
                'liability': Account.objects.get(special_type=Account.SpecialType.STATE_TAXES_PAYABLE),
                'description': 'State Income Tax'
            },
            self.Type.FEDERAL: {
                'expense': Account.objects.get(special_type=Account.SpecialType.FEDERAL_TAXES),
                'liability': Account.objects.get(special_type=Account.SpecialType.FEDERAL_TAXES_PAYABLE),
                'description': 'Federal Income Tax'

            },
            self.Type.PROPERTY: {
                'expense': Account.objects.get(special_type=Account.SpecialType.PROPERTY_TAXES),
                'liability': Account.objects.get(special_type=Account.SpecialType.PROPERTY_TAXES_PAYABLE),
                'description': 'Property Tax'
            }
        }

        accounts = tax_accounts[self.type]

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

        super().save(*args, **kwargs)

        try:
            journal_entry = self.transaction.journal_entry
        except JournalEntry.DoesNotExist:
            journal_entry = JournalEntry.objects.create(
                date=self.date,
                transaction=self.transaction
            )

        journal_entry_items = JournalEntryItem.objects.filter(journal_entry=journal_entry)
        journal_entry_items.delete()

        debit = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=self.transaction.amount,
            account=accounts['expense']
        )

        credit = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.CREDIT,
            amount=self.transaction.amount,
            account=accounts['liability']
        )

        # Update the Reconciliation per the new tax amount
        liability_account = accounts['liability']
        liability_balance = liability_account.get_balance(self.date)
        try:
            reconciliation = Reconciliation.objects.get(date=self.date, account=accounts['liability'])
            reconciliation.amount = liability_balance
            reconciliation.save()
        except Reconciliation.DoesNotExist:
            pass

class Account(models.Model):

    class SpecialType(models.TextChoices):
        UNREALIZED_GAINS_AND_LOSSES = 'unrealized_gains_and_losses', _('Unrealized Gains and Losses')
        STATE_TAXES_PAYABLE = 'state_taxes_payable', _('State Taxes Payable')
        FEDERAL_TAXES_PAYABLE = 'federal_taxes_payable', _('Federal Taxes Payable')
        PROPERTY_TAXES_PAYABLE = 'property_taxes_payable', _('Property Taxes Payable')
        STATE_TAXES = 'state_taxes', _('State Taxes')
        FEDERAL_TAXES = 'federal_taxes', _('Federal Taxes')
        PROPERTY_TAXES = 'property_taxes', _('Property Taxes')

    class Type(models.TextChoices):
        ASSET = 'asset', _('Asset')
        LIABILITY = 'liability', _('Liability')
        INCOME = 'income', _('Income')
        EXPENSE = 'expense', _('Expense')
        EQUITY = 'equity', _('Equity')

    class SubType(models.TextChoices):
        # Liability types
        SHORT_TERM_DEBT = 'short_term_debt', _('Short-term Debt')
        LONG_TERM_DEBT = 'long_term_debt', _('Long-term Debt')
        TAXES_PAYABLE = 'taxes_payable', _('Taxes Payable')
        # Asset types
        CASH = 'cash', _('Cash')
        REAL_ESTATE = 'real_estate', _('Real Estate')
        SECURITIES_RETIREMENT = 'securities_retirement', _('Securities-Retirement')
        SECURITIES_UNRESTRICTED = 'securities_unrestricted', _('Securities-Unrestricted')
        # Equity types
        RETAINED_EARNINGS = 'retained_earnings', _('Retained Earnings')
        # Income types
        UNREALIZED_INVESTMENT_GAINS = 'unrealized_investment_gains', _('Unrealized Investment Gains')
        REALIZED_INVESTMENT_GAINS = 'realized_investment_gains', _('Realized Investment Gains')
        SALARY = 'salary', _('Salary')
        DIVIDENDS_AND_INTEREST = 'dividends_and_interest', _('Dividends & Interest')
        OTHER_INCOME = 'other_income', _('Other Income')
        # Expense Types
        PURCHASES = 'purchases', _('Purchases')
        TAX = 'tax', _('Tax')
        INTEREST = 'interest', _('Interest Expense')
        ACCOUNTS_RECEIVABLE = 'accounts_receivable', _('Accounts Receivable')

    name = models.CharField(max_length=200,unique=True)
    type = models.CharField(max_length=9,choices=Type.choices)
    sub_type = models.CharField(max_length=30,choices=SubType.choices)
    csv_profile = models.ForeignKey('CSVProfile',related_name='accounts',on_delete=models.PROTECT,null=True,blank=True)
    special_type = models.CharField(max_length=30,choices=SpecialType.choices, null=True, blank=True, unique=True)

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
        INCOME_STATEMENT_ACCOUNT_TYPES = ['income','expense']

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
            if journal_entry_item.type == JournalEntryItem.JournalEntryType.DEBIT:
                debits += amount
            else:
                credits += amount

        return Account.get_balance_from_debit_and_credit(account_type=self.type,debits=debits,credits=credits)

class JournalEntry(models.Model):
    date = models.DateField()
    description = models.CharField(max_length=200,blank=True)
    transaction = models.OneToOneField('Transaction',related_name='journal_entry',on_delete=models.CASCADE)

    def __str__(self):
        return str(self.pk) + ': ' + str(self.date) + ' ' + self.description

class JournalEntryItem(models.Model):

    class JournalEntryType(models.TextChoices):
        DEBIT = 'debit', _('Debit')
        CREDIT = 'credit', _('Credit')

    journal_entry = models.ForeignKey('JournalEntry',related_name='journal_entry_items',on_delete=models.CASCADE)
    type = models.CharField(max_length=6,choices=JournalEntryType.choices)
    amount = models.DecimalField(decimal_places=2,max_digits=12)
    account = models.ForeignKey('Account',on_delete=models.CASCADE)

    def __str__(self):
        return str(self.journal_entry.id) + ' ' + self.type + ' $' + str(self.amount)

class AutoTag(models.Model):
    search_string = models.CharField(max_length=20)
    account = models.ForeignKey('Account',on_delete=models.CASCADE,null=True,blank=True)
    transaction_type = models.CharField(max_length=25,choices=Transaction.TransactionType.choices,blank=True)

    def __str__(self):
        return '"' + self.search_string +  '": ' + str(self.account)

class CSVColumnValuePair(models.Model):
    column = models.CharField(max_length=200)
    value = models.CharField(max_length=200)

class CSVProfile(models.Model):
    name = models.CharField(max_length=200)
    date = models.CharField(max_length=200)
    description = models.CharField(max_length=200)
    category = models.CharField(max_length=200)
    clear_prepended_until_value = models.CharField(max_length=200, blank=True)
    clear_values_column_pairs = models.ManyToManyField(CSVColumnValuePair, null=True, blank=True)
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
            transactions_list.append(
                Transaction.objects.create(
                    date=self._get_formatted_date(row[self.date]),
                    account=account,
                    amount=self._get_coalesced_amount(row),
                    description=row[self.description],
                    category=row[self.category]
                )
            )

        return transactions_list

    def _get_formatted_date(self, date_string):
        # Parse the original date using the input format
        original_date = datetime.datetime.strptime(date_string, self.date_format)

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
        list_of_dicts = [dict(zip(trimmed_headings, row)) for row in list_of_lists[1:]]
        return list_of_dicts

    def _clear_extraneous_rows(self, rows_list):
        cleaned_rows = []
        for row in rows_list:
            for key_clear_pair in self.clear_values_column_pairs.all():
                column_name = key_clear_pair.column
                clear_out_value = key_clear_pair.value
                try:
                    if row[column_name] == clear_out_value:
                        continue
                except KeyError:
                    continue
            cleaned_rows.append(row)

        return cleaned_rows
