import csv
import calendar
from datetime import datetime, timedelta, date
from django import forms
from django.forms import BaseModelFormSet
from django.utils import timezone
from django.core.validators import RegexValidator
from api.models import Transaction, Account, JournalEntryItem, TaxCharge, Reconciliation, CSVProfile

def _get_last_days_of_month_tuples():
    # Get the current year and month
    current_date = datetime.today()
    current_year = current_date.year
    current_month = current_date.month

    # Create a list of year-month tuples
    # For the current year, include months up to the current month.
    # For previous years, include all months.
    year_month_tuples = [(year, month) for year in range(2023, current_year + 1)
                         for month in range(1, current_month + 1 if year == current_year else 13)]

    final_days_of_month = []
    for year, month in year_month_tuples:
        # Calculate the first day of the next month
        next_month = month % 12 + 1
        next_month_year = year if month != 12 else year + 1

        # Calculate the last day of the current month
        last_day = date(next_month_year, next_month, 1) - timedelta(days=1)
        final_days_of_month.append((last_day, last_day.strftime('%B %d, %Y')))

    final_days_of_month.reverse()
    return final_days_of_month

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
        self.fields['date'].choices = _get_last_days_of_month_tuples()

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
            field.choices = _get_last_days_of_month_tuples()

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
    class Meta:
        model = TaxCharge
        fields = ['type','date','amount']

class TransactionLinkForm(forms.Form):
    first_transaction = forms.ModelChoiceField(
        queryset=Transaction.objects.all(),
        required=True,
        label='Base Transaction',
        widget=forms.HiddenInput()
    )
    second_transaction = forms.ModelChoiceField(
        queryset=Transaction.objects.all(),
        required=False,
        label='Linked Transaction',
        widget=forms.HiddenInput()
    )

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

    def save(self, transaction_id, type, commit=True):
        instances = []

        for form in self.forms:
            if form.is_valid() and form.has_changed():
                instance = form.save(transaction_id, type, commit=False)
                instances.append(instance)

                if commit:
                    instance.save()

        return instances

class JournalEntryItemForm(forms.ModelForm):
    amount = forms.DecimalField(
        initial=0.00,
        decimal_places=2,
        max_digits=12,
        validators=[
            RegexValidator(
                regex=r'^\d{1,10}(\.\d{1,2})?$',
                message="Enter a valid amount in dollars and cents format."
            )
        ],
        widget=forms.NumberInput(attrs={'step': '0.01'})
    )

    class Meta:
        model = JournalEntryItem
        fields = ('account', 'amount')

    def __init__(self, *args, **kwargs):
        super(JournalEntryItemForm, self).__init__(*args, **kwargs)
        self.fields['amount'].localize = True
        self.fields['amount'].widget.is_localized = True

    def save(self, journal_entry, type, commit=True):
        instance = super(JournalEntryItemForm, self).save(commit=False)

        instance.journal_entry = journal_entry
        instance.type = type
        instance.save()

        return instance

class TransactionFilterForm(forms.Form):
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'placeholder': 'Start Date', 'class': 'form-control'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'placeholder': 'End Date', 'class': 'form-control'})
    )
    account = forms.ModelMultipleChoiceField(
        queryset=Account.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control select2'})
    )
    transaction_type = forms.MultipleChoiceField(
        choices=Transaction.TransactionType.choices,
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control select2'})
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
        queryset = Transaction.objects.all()
        if self.cleaned_data.get('date_from'):
            queryset = queryset.filter(date__gte=self.cleaned_data['date_from'])
        if self.cleaned_data.get('date_to'):
            queryset = queryset.filter(date__lte=self.cleaned_data['date_to'])
        if self.cleaned_data.get('is_closed') is not None:
            queryset = queryset.filter(is_closed=self.cleaned_data['is_closed'])
        if self.cleaned_data['account']:
            queryset = queryset.filter(account__in=self.cleaned_data['account'])
        if self.cleaned_data['transaction_type']:
            queryset = queryset.filter(type__in=self.cleaned_data['transaction_type'])
        if self.cleaned_data.get('has_linked_transaction') is not None:
            queryset = queryset.exclude(linked_transaction__isnull=self.cleaned_data['has_linked_transaction'])

        return queryset.order_by('date','account')

class TransactionForm(forms.ModelForm):

    suggested_account = forms.ModelChoiceField(
        queryset=Account.objects.exclude(special_type=Account.SpecialType.WALLET)
    )

    class Meta:
        model = Transaction
        fields = ['date','amount','description','suggested_account']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'amount': forms.NumberInput(attrs={'step': '1'})
        }

    def __init__(self, *args, **kwargs):
        super(TransactionForm, self).__init__(*args, **kwargs)
        print(Account.objects.exclude(special_type=Account.SpecialType.WALLET))
        self.fields['date'].initial = timezone.localdate()  # Set today's date as initial value

    def save(self, *args, **kwargs):
        instance = super(TransactionForm, self).save(commit=False)
        wallet = Account.objects.get(special_type=Account.SpecialType.WALLET)

        instance.account = wallet
        instance.amount = instance.amount * -1
        instance.save()
        return instance
