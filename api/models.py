from django.db import models
from django.utils.translation import gettext_lazy as _

class Account(models.Model):

    class AccountType(models.TextChoices):
        ASSET = 'A', _('Asset')
        LIABILITY = 'L', _('Liability')
        INCOME = 'I', _('Income')
        EXPENSE = 'E', _('Expense')
        EQUITY = 'Q', _('Equity')

    name = models.CharField(max_length=200,unique=True)
    type = models.CharField(max_length=1,choices=AccountType.choices)

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
