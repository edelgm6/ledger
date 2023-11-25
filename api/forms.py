from django import forms
from django.forms import BaseModelFormSet
from django.utils import timezone
from django.core.validators import RegexValidator
from api.models import Transaction, Account, JournalEntryItem, TaxCharge

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
