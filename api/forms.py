from django import forms
from django.forms import BaseModelFormSet
from django.utils import timezone
from django.core.validators import RegexValidator
from api.models import Transaction, Account, JournalEntryItem, JournalEntry

class BaseJournalEntryItemFormset(BaseModelFormSet):
    def save(self, transaction_id, type, commit=True):
        instances = []

        for form in self.forms:
            # Make sure the form is valid and has changes
            if form.is_valid() and form.has_changed():
                # Pass the custom argument to the form's save method
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
        (None, '---------'),  # Display text for None value
        (True, 'True'),
        (False, 'False'),
    )
    is_closed = forms.ChoiceField(
        required=False,
        choices=IS_CLOSED_CHOICES
    )

    def clean_is_closed(self):
        is_closed = self.cleaned_data.get('is_closed', None)
        if is_closed == '':
            return None
        return is_closed

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
