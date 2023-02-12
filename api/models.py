from django.db import models
from django.utils.translation import gettext_lazy as _

class Account(models.Model):

    class AccountType(models.TextChoices):
        ASSET = 'asset', _('Asset')
        LIABILITY = 'liability', _('Liability')
        INCOME = 'income', _('Income')
        EXPENSE = 'expense', _('Expense')
        EQUITY = 'equity', _('Equity')

    class AccountSubType(models.TextChoices):
        CREDIT_CARD = 'credit_card', _('Credit Card')

    name = models.CharField(max_length=200,unique=True)
    type = models.CharField(max_length=9,choices=AccountType.choices)
    sub_type = models.CharField(max_length=30,choices=AccountSubType.choices)

    def __str__(self):
        return self.name

class Transaction(models.Model):
    date = models.DateField()
    account = models.ForeignKey('Account',on_delete=models.CASCADE)
    amount = models.DecimalField(decimal_places=2,max_digits=12)
    description = models.CharField(max_length=200)
    category = models.CharField(max_length=200)
    is_closed = models.BooleanField(default=False)
    date_closed = models.DateField(null=True,blank=True)

    def __str__(self):
        return str(self.date) + ' ' + self.account.name + ' ' + self.description + ' $' + str(self.amount)

    def close(self, date):
        self.is_closed = True
        self.date_closed = date
        self.save()

class JournalEntry(models.Model):
    date = models.DateField()
    description = models.CharField(max_length=200,blank=True)
    transaction = models.OneToOneField('Transaction',on_delete=models.CASCADE,null=True,blank=True)

    def __str__(self):
        return str(self.date) + ' ' + self.description

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
