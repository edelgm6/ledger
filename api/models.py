import datetime
from django.db import models
from django.db.models import Sum, Case, When, Value, DecimalField
from django.utils.translation import gettext_lazy as _

class Reconciliation(models.Model):
    account = models.ForeignKey('Account',on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(decimal_places=2,max_digits=12,null=True,blank=True)

    class Meta:
        unique_together = [['account','date']]

    def __str__(self):
        return str(self.date) + ' ' + self.account.name

    def plug_investment_change(self):
        GAIN_LOSS_ACCOUNT = '4050-Investment Gains or Losses'

        delta = self.amount - self.account.get_balance(self.date)

        journal_entry = JournalEntry.objects.create(
            date=self.date,
            description=str(self.date) + ' Plug gain/loss for ' + self.account.name
        )

        if delta > 0:
            gain_loss_entry_type = JournalEntryItem.JournalEntryType.CREDIT
            account_entry_type = JournalEntryItem.JournalEntryType.DEBIT
        else:
            gain_loss_entry_type = JournalEntryItem.JournalEntryType.DEBIT
            account_entry_type = JournalEntryItem.JournalEntryType.CREDIT

        gain_loss_entry = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=gain_loss_entry_type,
            amount=delta,
            account=Account.objects.get(name=GAIN_LOSS_ACCOUNT)
        )

        account_entry = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=account_entry_type,
            amount=delta,
            account=self.account
        )

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
    suggested_type = models.CharField(max_length=25,choices=TransactionType.choices,blank=True)
    linked_transaction = models.OneToOneField('Transaction',on_delete=models.CASCADE,null=True,blank=True)

    def __str__(self):
        return str(self.date) + ' ' + self.account.name + ' ' + self.description + ' $' + str(self.amount)

    def close(self, date):
        self.is_closed = True
        self.date_closed = date
        self.save()

class Account(models.Model):

    class AccountType(models.TextChoices):
        ASSET = 'asset', _('Asset')
        LIABILITY = 'liability', _('Liability')
        INCOME = 'income', _('Income')
        EXPENSE = 'expense', _('Expense')
        EQUITY = 'equity', _('Equity')

    class AccountSubType(models.TextChoices):
        SHORT_TERM_DEBT = 'short_term_debt', _('Short-term Debt')
        LONG_TERM_DEBT = 'long_term_debt', _('Long-term Debt')
        CASH = 'cash', _('Cash')
        REAL_ESTATE = 'real_estate', _('Real Estate')
        SECURITIES_RETIREMENT = 'securities_retirement', _('Securities-Retirement')
        SECURITIES_UNRESTRICTED = 'securities_unrestricted', _('Securities-Unrestricted')
        RETAINED_EARNINGS = 'retained_earnings', _('Retained Earnings')
        INVESTMENT_GAINS = 'investment_gains', _('Investment Gains')
        INCOME = 'income', _('Income')
        EXPENSE = 'expense', _('Expense')

    name = models.CharField(max_length=200,unique=True)
    type = models.CharField(max_length=9,choices=AccountType.choices)
    sub_type = models.CharField(max_length=30,choices=AccountSubType.choices)
    csv_profile = models.ForeignKey('CSVProfile',related_name='accounts',on_delete=models.PROTECT,null=True,blank=True)

    def __str__(self):
        return self.name

    @staticmethod
    def get_balance_from_aggregates(aggregates):
        account_balance_list = []
        for aggregate in aggregates:
            account_type = aggregate['account__type']
            debits = aggregate['debit_total']
            credits = aggregate['credit_total']

            if account_type in ['asset','expense']:
                balance = debits - credits
            else:
                balance = credits - debits

            account_balance_list.append(
                {
                    'account': aggregate['account__name'],
                    'balance': balance,
                    'type': account_type,
                    'sub_type': aggregate['account__sub_type']
                }
            )

        sorted_list = sorted(account_balance_list, key=lambda k: k['account'])
        return sorted_list

    @staticmethod
    def get_balance_sheet_balances(end_date):
        BALANCE_SHEET_ACCOUNT_TYPES = ['asset','liability','equity']
        balance_sheet_aggregates = JournalEntryItem.objects.filter(
            account__type__in=BALANCE_SHEET_ACCOUNT_TYPES,
            journal_entry__date__lte=end_date
            ).values('account__name','account__type','account__sub_type').annotate(
                debit_total=Sum(
                    Case(
                        When(type='debit', then='amount'),
                        output_field=DecimalField(),
                        default=Value(0)
                    )
                ),
                credit_total=Sum(
                    Case(
                        When(type='credit', then='amount'),
                        output_field=DecimalField(),
                        default=Value(0)
                    )
                )
            )

        balances = Account.get_balance_from_aggregates(balance_sheet_aggregates)
        return balances

    @staticmethod
    def get_income_statement_balances(start_date, end_date):
        INCOME_STATEMENT_ACCOUNT_TYPES = ['income','expense']
        income_statement_aggregates = JournalEntryItem.objects.filter(
                account__type__in=INCOME_STATEMENT_ACCOUNT_TYPES,
                journal_entry__date__gte=start_date,
                journal_entry__date__lte=end_date
                ).values('account__name','account__type','account__sub_type').annotate(
                    debit_total=Sum(
                        Case(
                            When(type='debit', then='amount'),
                            output_field=DecimalField(),
                            default=Value(0)
                        )
                    ),
                    credit_total=Sum(
                        Case(
                            When(type='credit', then='amount'),
                            output_field=DecimalField(),
                            default=Value(0)
                        )
                    )
                )
        balances = Account.get_balance_from_aggregates(income_statement_aggregates)

        net_income = 0
        for balance in balances:
            if balance['type'] == Account.AccountType.INCOME:
                net_income += balance['balance']
            else:
                net_income -= balance['balance']

        NET_INCOME_ACCOUNT_NAME = '3010-Net Income'
        balances.append(
            {
                'account': NET_INCOME_ACCOUNT_NAME,
                'balance': net_income,
                'type': Account.AccountType.EQUITY,
                'sub_type': Account.AccountSubType.RETAINED_EARNINGS
            }
        )

        return balances

    @staticmethod
    def get_account_balances(start_date, end_date):
        income_statement_balances = Account.get_income_statement_balances(start_date, end_date)
        balance_sheet_balances = Account.get_balance_sheet_balances(end_date)

        return balance_sheet_balances + income_statement_balances

    def get_balance(self, end_date, start_date=None):
        if not start_date:
            start_date = end_date - datetime.timedelta(days=1)
        account_balances = self.get_account_balances(start_date, end_date)
        balance = [balance for balance in account_balances if balance['account'] == self.name][0]['balance']
        return balance

class JournalEntry(models.Model):
    date = models.DateField()
    description = models.CharField(max_length=200,blank=True)
    transaction = models.OneToOneField('Transaction',on_delete=models.CASCADE,null=True,blank=True)

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

class CSVProfile(models.Model):
    name = models.CharField(max_length=200)
    date = models.CharField(max_length=200)
    amount = models.CharField(max_length=200)
    description = models.CharField(max_length=200)
    category = models.CharField(max_length=200)
    account = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.name
