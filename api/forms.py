import csv
from decimal import Decimal, InvalidOperation

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.forms import BaseModelFormSet, DecimalField
from django.utils import timezone

from api import utils
from api.aws_services import upload_file_to_s3
from api.factories import ReconciliationFactory
from api.models import (
    Account,
    Amortization,
    Entity,
    JournalEntry,
    JournalEntryItem,
    Prefill,
    Reconciliation,
    S3File,
    TaxCharge,
    Transaction,
)


class JournalEntryItemEntityForm(forms.ModelForm):
    entity = forms.ModelChoiceField(
        queryset=Entity.objects.all().order_by("name"), required=True
    )

    class Meta:
        model = JournalEntryItem
        fields = [
            "entity",
        ]


class DocumentForm(forms.Form):
    document = forms.FileField()
    prefill = forms.ModelChoiceField(
        queryset=Prefill.objects.filter(docsearch__isnull=False).distinct(),
        required=True,
    )

    def create_s3_file(self):
        file = self.cleaned_data["document"]
        unique_name = upload_file_to_s3(file=file)
        file_url = (
            f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{unique_name}"
        )
        s3file = S3File.objects.create(
            prefill=self.cleaned_data["prefill"],
            url=file_url,
            user_filename=file.name,
            s3_filename=unique_name,
        )
        return s3file


class CommaDecimalField(DecimalField):
    def to_python(self, value):
        if value is None or "":
            return value
        try:
            value = str(value).replace(",", "")
            value = str(value).replace("$", "")
            value = Decimal(value)
        except InvalidOperation:
            return None
        return super().to_python(value)


class FromToDateForm(forms.Form):
    date_from = forms.DateField(required=False)
    date_to = forms.DateField()

    def __init__(self, *args, **kwargs):
        super(FromToDateForm, self).__init__(*args, **kwargs)
        last_days_of_month_tuples = utils.get_last_days_of_month_tuples()
        last_day_of_last_month = last_days_of_month_tuples[0][0]

        self.fields["date_from"].initial = utils.format_datetime_to_string(
            utils.get_first_day_of_month_from_date(last_day_of_last_month)
        )
        self.fields["date_to"].initial = utils.format_datetime_to_string(
            last_day_of_last_month
        )


class DateForm(forms.Form):
    date = forms.ChoiceField()

    def __init__(self, *args, **kwargs):
        super(DateForm, self).__init__(*args, **kwargs)
        last_days_of_month_tuples = utils.get_last_days_of_month_tuples()
        self.fields["date"].choices = last_days_of_month_tuples
        self.fields["date"].initial = last_days_of_month_tuples[0][0]


class AmortizationForm(forms.ModelForm):
    accrued_journal_entry_item = forms.ModelChoiceField(
        queryset=JournalEntryItem.objects.all(), widget=forms.HiddenInput()
    )
    suggested_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(type=Account.Type.EXPENSE)
    )

    class Meta:
        model = Amortization
        fields = [
            "accrued_journal_entry_item",
            "periods",
            "description",
            "suggested_account",
        ]

    def clean_periods(self):
        periods = self.cleaned_data["periods"]

        if periods < 1:
            raise ValidationError("Periods must be >= 1")

        return periods

    def save(self, commit=True):
        instance = super(AmortizationForm, self).save(commit=False)
        journal_entry_item = self.cleaned_data["accrued_journal_entry_item"]
        instance.amount = abs(journal_entry_item.amount)

        if commit:
            instance.save()
        return instance


class UploadTransactionsForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=Account.objects.filter(csv_profile__isnull=False)
    )
    transaction_csv = forms.FileField()

    def _csv_to_list_of_lists(self, csvfile):
        # Open the file in text mode with the correct encoding
        decoded_file = csvfile.read().decode("utf-8").splitlines()
        csv_reader = csv.reader(decoded_file)
        list_of_lists = list(csv_reader)
        return list_of_lists

    def save(self):
        account = self.cleaned_data["account"]
        csv_profile = account.csv_profile
        transaction_list = self._csv_to_list_of_lists(
            self.cleaned_data["transaction_csv"]
        )
        transactions = csv_profile.create_transactions_from_csv(
            transaction_list, account
        )
        return transactions


class ReconciliationFilterForm(forms.Form):
    date = forms.ChoiceField()

    def __init__(self, *args, **kwargs):
        super(ReconciliationFilterForm, self).__init__(*args, **kwargs)
        self.fields["date"].choices = utils.get_last_days_of_month_tuples()

    def get_reconciliations(self):
        return Reconciliation.objects.filter(date=self.cleaned_data["date"])

    def generate_reconciliations(self, create_date=None):
        create_date = create_date if create_date else self.cleaned_data["date"]
        reconciliations = ReconciliationFactory.create_bulk_reconciliations(
            date=create_date
        )
        return reconciliations


class ReconciliationForm(forms.ModelForm):
    amount = CommaDecimalField(
        initial=0.00,
        decimal_places=2,
        max_digits=12,
        widget=forms.NumberInput(attrs={"step": "0.01"}),
        required=False,
    )

    class Meta:
        model = Reconciliation
        fields = ["amount"]


class TaxChargeFilterForm(forms.Form):

    date_from = forms.ChoiceField(required=False, choices=[])
    date_to = forms.ChoiceField(required=False, choices=[])
    TAX_TYPE_CHOICES = (
        (None, "---------"),
        (TaxCharge.Type.FEDERAL, "Federal"),
        (TaxCharge.Type.STATE, "State"),
        (TaxCharge.Type.PROPERTY, "Property"),
    )
    tax_type = forms.ChoiceField(required=False, choices=TAX_TYPE_CHOICES)

    def __init__(self, *args, **kwargs):
        super(TaxChargeFilterForm, self).__init__(*args, **kwargs)
        # Restrict both fields to only allow last days of months
        last_days_of_month_tuples = utils.get_last_days_of_month_tuples()
        for field_name in ["date_from", "date_to"]:
            field = self.fields[field_name]
            field.choices = last_days_of_month_tuples

        six_months_ago_date_string = last_days_of_month_tuples[5][0]
        self.fields["date_from"].initial = six_months_ago_date_string

    def get_tax_charges(self):
        queryset = TaxCharge.objects.all()
        if self.cleaned_data.get("date_to"):
            queryset = queryset.filter(date__gte=self.cleaned_data["date_from"])
        if self.cleaned_data.get("date_from"):
            queryset = queryset.filter(date__lte=self.cleaned_data["date_to"])
        if self.cleaned_data["tax_type"]:
            queryset = queryset.filter(type=self.cleaned_data["tax_type"])

        return queryset.order_by("date")


class TaxChargeForm(forms.ModelForm):
    date = forms.ChoiceField(required=False, choices=[])
    amount = CommaDecimalField(
        initial=0.00,
        decimal_places=2,
        max_digits=12,
        validators=[MinValueValidator(Decimal("0.00"))],
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )

    class Meta:
        model = TaxCharge
        fields = ["type", "date", "amount"]

    def __init__(self, *args, **kwargs):
        super(TaxChargeForm, self).__init__(*args, **kwargs)
        last_days_of_month_tuples = utils.get_last_days_of_month_tuples()
        self.fields["date"].choices = last_days_of_month_tuples
        last_day_of_last_month = last_days_of_month_tuples[0][0]
        self.fields["date"].initial = last_day_of_last_month


class TransactionLinkForm(forms.Form):
    first_transaction = forms.ModelChoiceField(
        queryset=Transaction.objects.all(),
        required=True,
        label="Base Transaction",
        widget=forms.HiddenInput(),
    )
    second_transaction = forms.ModelChoiceField(
        queryset=Transaction.objects.all(),
        required=True,
        label="Linked Transaction",
        widget=forms.HiddenInput(),
    )

    def clean(self):
        cleaned_data = super().clean()

        amount1 = self.cleaned_data.get("first_transaction").amount
        amount2 = self.cleaned_data.get("second_transaction").amount

        # Validate that amount1 is the negative of amount2
        if amount1 != amount2 * -1:
            error_message = "The amount of the first transaction must be the \
                negative of the second transaction."
            raise forms.ValidationError(error_message)

        return cleaned_data

    def save(self):
        first_transaction = self.cleaned_data.get("first_transaction")
        second_transaction = self.cleaned_data.get("second_transaction")

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


class JournalEntryMetadataForm(forms.Form):
    index = forms.IntegerField(min_value=0, widget=forms.HiddenInput())
    paystub_id = forms.CharField(widget=forms.HiddenInput(), required=False)


class BaseJournalEntryItemFormset(BaseModelFormSet):

    def __init__(self, *args, **kwargs):
        open_accounts = Account.objects.filter(is_closed=False)
        open_accounts_choices = [
            (account.name, account.name) for account in open_accounts
        ]

        open_entities = Entity.objects.filter(is_closed=False)
        open_entities_choices = [entity.name for entity in open_entities]
        kwargs["form_kwargs"] = {
            "open_accounts_choices": open_accounts_choices,
            "open_entities_choices": open_entities_choices,
        }
        super(BaseJournalEntryItemFormset, self).__init__(*args, **kwargs)

    def get_entry_total(self):
        total = 0
        for form in self.forms:
            try:
                amount = form.cleaned_data.get("amount")
            except AttributeError:
                amount = form.initial.get("amount", None)
            total += amount if amount is not None else 0

        return total

    def get_account_amount(self, target_account):
        for form in self.forms:
            account = form.cleaned_data.get("account")
            if account == target_account:
                return form.cleaned_data.get("amount")

    def save(self, transaction, type, commit=True):

        try:
            journal_entry = transaction.journal_entry
        except JournalEntry.DoesNotExist:
            journal_entry = JournalEntry.objects.create(
                date=transaction.date, transaction=transaction
            )

        instances = []
        for form in self.forms:
            if (
                form.is_valid()
                and form.has_changed()
                and form.cleaned_data["amount"] > 0
            ):
                instance = form.save(journal_entry, type)
                instances.append(instance)

        return instances


class JournalEntryItemForm(forms.ModelForm):
    amount = CommaDecimalField(
        initial=0.00,
        decimal_places=2,
        max_digits=12,
        validators=[MinValueValidator(Decimal("0.00"))],
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
    account = forms.ChoiceField(choices=[])
    # entity = forms.ChoiceField(choices=[])
    entity = forms.CharField()

    class Meta:
        model = JournalEntryItem
        fields = ("account", "amount", "entity")

    def __init__(self, *args, **kwargs):
        open_accounts_choices = kwargs.pop("open_accounts_choices", [])
        open_entities_choices = kwargs.pop("open_entities_choices", [])
        super(JournalEntryItemForm, self).__init__(*args, **kwargs)
        self.fields["amount"].localize = True
        self.fields["account"].choices = open_accounts_choices
        # self.fields["entity"].choices = open_entities_choices
        self.entity_choices = open_entities_choices

        # Resolve the account name for the bound form
        if self.instance.pk and self.instance.account:
            self.account_name = self.instance.account.name
        else:
            self.account_name = ""

        # Resolve the entity name for the bound form
        if self.instance.pk and self.instance.entity:
            self.entity_name = self.instance.entity.name
        else:
            self.entity_name = ""

    def clean_account(self):
        account_name = self.cleaned_data["account"]
        try:
            account = Account.objects.get(name=account_name)
            return account
        except Account.DoesNotExist:
            raise forms.ValidationError("This Account does not exist.")

    def clean_entity(self):
        entity_name = self.cleaned_data["entity"]
        entity, created = Entity.objects.get_or_create(name=entity_name)

        if created:
            self.created_entity = entity

        return entity

    def save(self, journal_entry, type):
        instance = super(JournalEntryItemForm, self).save(commit=False)

        instance.journal_entry = journal_entry
        instance.type = type
        instance.save()

        return instance


class TransactionFilterForm(forms.Form):
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)
    account = forms.ModelMultipleChoiceField(
        queryset=Account.objects.all(), required=False
    )
    transaction_type = forms.MultipleChoiceField(
        choices=Transaction.TransactionType.choices, required=False
    )
    IS_CLOSED_CHOICES = (
        (None, "---------"),
        (True, "True"),
        (False, "False"),
    )
    is_closed = forms.ChoiceField(required=False, choices=IS_CLOSED_CHOICES)
    LINKED_TRANSACTION_CHOICES = (
        (None, "---------"),
        (True, "Linked"),
        (False, "Unlinked"),
    )
    has_linked_transaction = forms.ChoiceField(
        required=False, choices=LINKED_TRANSACTION_CHOICES
    )
    related_account = forms.ModelMultipleChoiceField(
        queryset=Account.objects.all(), required=False
    )

    def clean_is_closed(self):
        is_closed = self.cleaned_data.get("is_closed", None)
        if is_closed == "":
            return None
        return is_closed

    def clean_has_linked_transaction(self):
        data = self.cleaned_data["has_linked_transaction"]
        if data in ["True", "False"]:
            return data == "True"
        return None

    def get_transactions(self):
        data = self.cleaned_data
        queryset = Transaction.objects.filter_for_table(
            is_closed=data.get("is_closed"),
            has_linked_transaction=data.get("has_linked_transaction"),
            transaction_types=data["transaction_type"],
            accounts=data["account"],
            date_from=data.get("date_from"),
            date_to=data.get("date_to"),
            related_accounts=data["related_account"],
        ).select_related("account")
        return queryset


class TransactionForm(forms.ModelForm):

    account = forms.ChoiceField(choices=[])
    suggested_account = forms.ChoiceField(choices=[], required=False)
    amount = CommaDecimalField(
        initial=0.00,
        decimal_places=2,
        max_digits=12,
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )

    class Meta:
        model = Transaction
        fields = [
            "date",
            "account",
            "amount",
            "description",
            "suggested_account",
            "type",
        ]

    def __init__(self, *args, **kwargs):
        super(TransactionForm, self).__init__(*args, **kwargs)
        # Set today's date as initial value
        self.fields["date"].initial = timezone.localdate()
        # Remove the 'None' option
        self.fields["type"].choices = Transaction.TransactionType.choices
        eligible_accounts = Account.objects.exclude(
            special_type__in=[Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES],
        ).filter(is_closed=False)
        account_tuples = [(account.name, account.name) for account in eligible_accounts]
        self.fields["suggested_account"].choices = account_tuples
        self.fields["account"].choices = account_tuples

        # Resolve the account name for the bound form
        if self.instance.pk and self.instance.account:
            self.account_name = self.instance.account.name
        else:
            self.account_name = ""

        if self.instance.pk and self.instance.suggested_account:
            self.suggested_account_name = self.instance.suggested_account.name
        else:
            self.suggested_account_name = ""

    def clean_account(self):
        account_name = self.cleaned_data["account"]
        account = Account.objects.get(name=account_name)
        return account

    def clean_suggested_account(self):
        if not self.cleaned_data["suggested_account"]:
            return None
        suggested_account_name = self.cleaned_data["suggested_account"]
        suggested_account = Account.objects.get(name=suggested_account_name)
        return suggested_account


class WalletForm(forms.ModelForm):

    suggested_account = forms.ChoiceField(choices=[])

    class Meta:
        model = Transaction
        fields = ["date", "amount", "description", "suggested_account", "type"]

    def __init__(self, *args, **kwargs):
        super(WalletForm, self).__init__(*args, **kwargs)
        self.fields["date"].initial = timezone.localdate()

        # Override the 'type' field choices
        type_choices = [
            (Transaction.TransactionType.PURCHASE, "Purchase"),
            (Transaction.TransactionType.INCOME, "Income"),
        ]
        self.fields["type"].choices = type_choices
        self.fields["type"].initial = Transaction.TransactionType.PURCHASE
        eligible_accounts = Account.objects.filter(
            type__in=[Account.Type.INCOME, Account.Type.EXPENSE]
        ).exclude(special_type=Account.SpecialType.WALLET)
        self.fields["suggested_account"].choices = [
            (account.name, account.name) for account in eligible_accounts
        ]

    def clean_suggested_account(self):
        suggested_account_name = self.cleaned_data["suggested_account"]
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
