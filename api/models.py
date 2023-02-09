from django.db import models
from django.utils.translation import gettext_lazy as _

class Account(models.Model):

    class AccountType(models.TextChoices):
        ASSET = 'A', _('Asset')
        LIABILITY = 'L', _('Liability')
        INCOME = 'I', _('Income')
        EXPENSE = 'E', _('Expense')
        EQUITY = 'Q', _('Equity')

    name = models.CharField(max_length=200)
    number = models.PositiveIntegerField()
    type = models.CharField(max_length=1,choices=AccountType.choices)

class Transaction(models.Model):
    date = models.DateField()
    party = models.CharField(max_length=200)
    source = models.CharField(max_length=200)
    amount = models.DecimalField(decimal_places=2,max_digits=12)
    description = models.CharField(max_length=200)
    is_closed = models.BooleanField()
    date_closed = models.DateField()

class JournalEntry(models.Model):
    date = models.DateField()
    description = models.CharField(max_length=200)
    journal_entry = models.OneToOneField('Transaction',on_delete=models.CASCADE,null=True,blank=True)

class JournalEntryItems(models.Model):

    class JournalEntryType(models.TextChoices):
        DEBIT = 'D', _('Debit')
        CREDIT = 'C', _('Credit')

    journel_entry = models.ForeignKey('JournalEntry',on_delete=models.CASCADE)
    type = models.CharField(max_length=1,choices=JournalEntryType.choices)
    amount = models.DecimalField(decimal_places=2,max_digits=12)
    account = models.ForeignKey('Account',on_delete=models.CASCADE)
