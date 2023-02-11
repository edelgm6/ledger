from django import forms

class TransactionsUploadForm(forms.Form):
    file = forms.FileField()
    account = forms.CharField()