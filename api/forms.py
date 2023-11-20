from django import forms
from django.utils import timezone
from django.core.validators import RegexValidator
from api.models import Transaction, Account, JournalEntryItem

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
