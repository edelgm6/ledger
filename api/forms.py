import csv
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from django import forms
from django.forms import BaseModelFormSet, DecimalField
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from api.models import Amortization, Transaction, Account, JournalEntryItem, TaxCharge, Reconciliation, JournalEntry
from api import utils

class DateForm(forms.Form):
    date = forms.ChoiceField()

    def __init__(self, *args, **kwargs):
        super(DateForm, self).__init__(*args, **kwargs)
        last_days_of_month_tuples = utils.get_last_days_of_month_tuples()
        self.fields['date'].choices = last_days_of_month_tuples
        self.fields['date'].initial = last_days_of_month_tuples[0][0]

class AmortizationForm(forms.ModelForm):
    accrued_transaction = forms.ModelChoiceField(queryset=Transaction.objects.all(), widget=forms.HiddenInput())
    suggested_account = forms.ModelChoiceField(queryset=Account.objects.filter(type=Account.Type.EXPENSE))

    class Meta:
        model = Amortization
        fields = ['accrued_transaction','periods','description','suggested_account']

    def clean_periods(self):
        periods = self.cleaned_data['periods']

        if periods < 1:
            raise ValidationError('Periods must be >= 1')

        return periods

    def save(self, commit=True):
        instance = super(AmortizationForm, self).save(commit=False)
        transaction = self.cleaned_data['accrued_transaction']
        instance.amount = abs(transaction.amount)

        if commit:
            instance.save()
        return instance

class UploadTransactionsForm(forms.Form):
    account = forms.ModelChoiceField(queryset=Account.objects.filter(csv_profile__isnull=False))
    transaction_csv = forms.FileField()

    def _csv_to_list_of_lists(self, csvfile):
        # Open the file in text mode with the correct encoding
        decoded_file = csvfile.read().decode('utf-8').splitlines()
        csv_reader = csv.reader(decoded_file)
        list_of_lists = list(csv_reader)
        return list_of_lists

    def save(self):
        account = self.cleaned_data['account']
        csv_profile = account.csv_profile
        transaction_list = self._csv_to_list_of_lists(self.cleaned_data['transaction_csv'])
        transactions = csv_profile.create_transactions_from_csv(transaction_list,account)
        return transactions


class ReconciliationFilterForm(forms.Form):
    date = forms.ChoiceField()

    def __init__(self, *args, **kwargs):
        super(ReconciliationFilterForm, self).__init__(*args, **kwargs)
        self.fields['date'].choices = utils.get_last_days_of_month_tuples()

    def get_reconciliations(self):
        return Reconciliation.objects.filter(date=self.cleaned_data['date'])

    def generate_reconciliations(self):
        date = self.cleaned_data['date']

        balance_sheet_accounts = Account.objects.filter(type__in=[Account.Type.ASSET,Account.Type.LIABILITY])
        reconciliation_list = []
        for account in balance_sheet_accounts:
            reconciliation_list.append(
                Reconciliation(
                    account=account,
                    date=date
                )
            )

        reconciliations = Reconciliation.objects.bulk_create(reconciliation_list)
        return reconciliations

class ReconciliationForm(forms.ModelForm):
    class Meta:
        model = Reconciliation
        fields = ['amount']

class TaxChargeFilterForm(forms.Form):

    date_from = forms.ChoiceField(
        required=False,
        choices=[]
    )
    date_to = forms.ChoiceField(
        required=False,
        choices=[]
    )
    TAX_TYPE_CHOICES = (
        (None, '---------'),
        (TaxCharge.Type.FEDERAL, 'Federal'),
        (TaxCharge.Type.STATE, 'State'),
        (TaxCharge.Type.PROPERTY, 'Property')
    )
    tax_type = forms.ChoiceField(
        required=False,
        choices=TAX_TYPE_CHOICES
    )

    def __init__(self, *args, **kwargs):
        super(TaxChargeFilterForm, self).__init__(*args, **kwargs)
        # Restrict both fields to only allow last days of months
        for field_name in ['date_from', 'date_to']:
            field = self.fields[field_name]
            field.choices = utils.get_last_days_of_month_tuples()

        current_year = datetime.now().year
        january_31 = date(current_year, 1, 31)
        self.fields['date_from'].initial = january_31

    def get_tax_charges(self):
        queryset = TaxCharge.objects.all()
        if self.cleaned_data.get('date_to'):
            queryset = queryset.filter(date__gte=self.cleaned_data['date_from'])
        if self.cleaned_data.get('date_from'):
            queryset = queryset.filter(date__lte=self.cleaned_data['date_to'])
        if self.cleaned_data['tax_type']:
            queryset = queryset.filter(type=self.cleaned_data['tax_type'])

        return queryset.order_by('date')

class TaxChargeForm(forms.ModelForm):
    date = forms.ChoiceField(
        required=False,
        choices=[]
    )

    class Meta:
        model = TaxCharge
        fields = ['type','date','amount']

    def __init__(self, *args, **kwargs):
        super(TaxChargeForm, self).__init__(*args, **kwargs)
        last_days_of_month_tuples = utils.get_last_days_of_month_tuples()
        self.fields['date'].choices = last_days_of_month_tuples
        last_day_of_last_month = last_days_of_month_tuples[0][0]
        self.fields['date'].initial = last_day_of_last_month


class TransactionLinkForm(forms.Form):
    first_transaction = forms.ModelChoiceField(
        queryset=Transaction.objects.all(),
        required=True,
        label='Base Transaction',
        widget=forms.HiddenInput()
    )
    second_transaction = forms.ModelChoiceField(
        queryset=Transaction.objects.all(),
        required=True,
        label='Linked Transaction',
        widget=forms.HiddenInput()
    )

    def clean(self):
        cleaned_data = super().clean()

        amount1 = self.cleaned_data.get('first_transaction').amount
        amount2 = self.cleaned_data.get('second_transaction').amount

        # Validate that amount1 is the negative of amount2
        if amount1 != amount2 * -1:
            raise forms.ValidationError("The amount of the first transaction must be the negative of the second transaction.")

        return cleaned_data

    def save(self):
        first_transaction = self.cleaned_data.get('first_transaction')
        second_transaction = self.cleaned_data.get('second_transaction')

        if first_transaction.date < second_transaction.date:
            hero_transaction = first_transaction
            linked_transaction = second_transaction
        elif second_transaction.date < first_transaction.date:
            hero_transaction = second_transaction
            linked_transaction = first_transaction
        elif first_transaction.amount < 0:
            hero_transaction = first_transaction
            linked_transaction = second_transaction
        else:
            hero_transaction = second_transaction
            linked_transaction = first_transaction

        hero_transaction.create_link(linked_transaction)
        return hero_transaction

class BaseJournalEntryItemFormset(BaseModelFormSet):

    def get_entry_total(self):
        total = 0
        for form in self.forms:
            amount = form.cleaned_data.get('amount')
            total += (amount if amount is not None else 0)

        return total

    def get_account_amount(self, target_account):
        for form in self.forms:
            account = form.cleaned_data.get('account')
            if account == target_account:
                return form.cleaned_data.get('amount')

    def save(self, transaction, type, commit=True):

        try:
            journal_entry = transaction.journal_entry
        except JournalEntry.DoesNotExist:
            journal_entry = JournalEntry.objects.create(
                date=transaction.date,
                transaction=transaction
            )

        instances = []
        for form in self.forms:
            if form.is_valid() and form.has_changed():
                instance = form.save(journal_entry, type, commit=False)
                instances.append(instance)

                if commit:
                    instance.save()

        return instances

class CommaDecimalField(DecimalField):
    def to_python(self, value):
        if value is None:
            return value
        try:
            # Remove commas and convert to Decimal
            value = Decimal(str(value).replace(',', ''))
        except InvalidOperation:
            raise forms.ValidationError('Enter a number.')
        return super().to_python(value)

class JournalEntryItemForm(forms.ModelForm):
    amount = CommaDecimalField(
        initial=0.00,
        decimal_places=2,
        max_digits=12,
        validators=[MinValueValidator(Decimal('0.00'))],
        widget=forms.NumberInput(attrs={'step': '0.01'})
    )
    account = forms.ChoiceField(choices=[])

    class Meta:
        model = JournalEntryItem
        fields = ('account', 'amount')

    def __init__(self, *args, **kwargs):
        super(JournalEntryItemForm, self).__init__(*args, **kwargs)
        self.fields['amount'].localize = True
        # self.fields['amount'].widget.is_localized = True
        self.fields['account'].choices = [(account.name, account.name) for account in Account.objects.all()]

        # Resolve the account name for the bound form
        if self.instance.pk and self.instance.account:
            self.account_name = self.instance.account.name
        else:
            self.account_name = ''

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        return Decimal(amount)

    def clean_account(self):
        account_name = self.cleaned_data['account']
        try:
            account = Account.objects.get(name=account_name)
            return account
        except Account.DoesNotExist:
            raise forms.ValidationError("This Account does not exist.")

    def save(self, journal_entry, type, commit=True):
        instance = super(JournalEntryItemForm, self).save(commit=False)

        instance.journal_entry = journal_entry
        instance.type = type
        instance.save()

        return instance

class TransactionFilterForm(forms.Form):
    date_from = forms.DateField(
        required=False
    )
    date_to = forms.DateField(
        required=False
    )
    account = forms.ModelMultipleChoiceField(
        queryset=Account.objects.all(),
        required=False
    )
    transaction_type = forms.MultipleChoiceField(
        choices=Transaction.TransactionType.choices,
        required=False
    )
    IS_CLOSED_CHOICES = (
        (None, '---------'),
        (True, 'True'),
        (False, 'False'),
    )
    is_closed = forms.ChoiceField(
        required=False,
        choices=IS_CLOSED_CHOICES
    )
    LINKED_TRANSACTION_CHOICES = (
        (None, '---------'),
        (True, 'Linked'),
        (False, 'Unlinked'),
    )
    has_linked_transaction = forms.ChoiceField(
        required=False,
        choices=LINKED_TRANSACTION_CHOICES
    )

    def clean_is_closed(self):
        is_closed = self.cleaned_data.get('is_closed', None)
        if is_closed == '':
            return None
        return is_closed
    def clean_has_linked_transaction(self):
        data = self.cleaned_data['has_linked_transaction']
        if data in ['True', 'False']:
            return data == 'True'
        return None


    def get_transactions(self):
        queryset = Transaction.objects.filter_for_table(
            is_closed=self.cleaned_data.get('is_closed'),
            has_linked_transaction=self.cleaned_data.get('has_linked_transaction'),
            transaction_types=self.cleaned_data['transaction_type'],
            accounts=self.cleaned_data['account'],
            date_from=self.cleaned_data.get('date_from'),
            date_to=self.cleaned_data.get('date_to')
        )
        return queryset

class TransactionForm(forms.ModelForm):

    account = forms.ChoiceField(choices=[])
    suggested_account = forms.ChoiceField(choices=[], required=False)

    class Meta:
        model = Transaction
        fields = ['date','account','amount','description','suggested_account','type']

    def __init__(self, *args, **kwargs):
        super(TransactionForm, self).__init__(*args, **kwargs)
        self.fields['date'].initial = timezone.localdate()  # Set today's date as initial value
        self.fields['type'].choices = Transaction.TransactionType.choices # Remove the 'None' option
        eligible_accounts = Account.objects.exclude(special_type__in=[Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES])
        account_tuples = [(account.name, account.name) for account in eligible_accounts]
        self.fields['suggested_account'].choices = account_tuples
        self.fields['account'].choices = account_tuples

        # Resolve the account name for the bound form
        if self.instance.pk and self.instance.account:
            self.account_name = self.instance.account.name
        else:
            self.account_name = ''

        if self.instance.pk and self.instance.suggested_account:
            self.suggested_account_name = self.instance.suggested_account.name
        else:
            self.suggested_account_name = ''

    def clean_account(self):
        account_name = self.cleaned_data['account']
        account = Account.objects.get(name=account_name)
        return account

    def clean_suggested_account(self):
        if not self.cleaned_data['suggested_account']:
            return None
        suggested_account_name = self.cleaned_data['suggested_account']
        suggested_account = Account.objects.get(name=suggested_account_name)
        return suggested_account

class WalletForm(forms.ModelForm):

    suggested_account = forms.ChoiceField(choices=[])

    class Meta:
        model = Transaction
        fields = ['date','amount','description','suggested_account','type']

    def __init__(self, *args, **kwargs):
        super(WalletForm, self).__init__(*args, **kwargs)
        self.fields['date'].initial = timezone.localdate()  # Set today's date as initial value

        # Override the 'type' field choices
        type_choices = [
            (Transaction.TransactionType.PURCHASE, 'Purchase'),
            (Transaction.TransactionType.INCOME, 'Income')
        ]
        self.fields['type'].choices = type_choices
        self.fields['type'].initial = Transaction.TransactionType.PURCHASE
        eligible_accounts = Account.objects.filter(
            type__in=[Account.Type.INCOME,Account.Type.EXPENSE]
        ).exclude(
            special_type=Account.SpecialType.WALLET
        )
        self.fields['suggested_account'].choices = [(account.name, account.name) for account in eligible_accounts]

    def clean_suggested_account(self):
        suggested_account_name = self.cleaned_data['suggested_account']
        suggested_account = Account.objects.get(name=suggested_account_name)
        return suggested_account

    def save(self, commit=True):
        instance = super(WalletForm, self).save(commit=False)

        if instance.type == Transaction.TransactionType.PURCHASE:
            instance.amount *= -1

        wallet = Account.objects.get(special_type=Account.SpecialType.WALLET)
        instance.account = wallet

        if commit:
            instance.save()

        return instance
