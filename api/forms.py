from django import forms
from django.utils import timezone
from api.models import Transaction, Account

class TransactionFilterForm(forms.Form):
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'placeholder': 'Start Date', 'class': 'form-control'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'placeholder': 'End Date', 'class': 'form-control'})
    )
    is_closed = forms.BooleanField(required=False)
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
