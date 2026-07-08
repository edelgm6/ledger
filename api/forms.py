import csv
from decimal import Decimal, InvalidOperation
from typing import Dict

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.forms import BaseModelFormSet, DecimalField
from django.utils import timezone

from api import utils
from api.factories import ReconciliationFactory
from api.services.tax_services import get_tax_accounts
from api.models import (
    Account,
    Amortization,
    AutoTag,
    CSVProfile,
    DocSearch,
    Entity,
    JournalEntry,
    JournalEntryItem,
    Loan,
    Prefill,
    Reconciliation,
    TaxCharge,
    Transaction,
    UtilityBillRule,
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
        queryset=Prefill.objects.filter(is_closed=False),
        required=True,
    )


class CommaDecimalField(DecimalField):
    def to_python(self, value):
        if value is None or "":
            return value
        try:
            value = utils.parse_currency(value)
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
    salvage_value = CommaDecimalField(
        required=False,
        decimal_places=2,
        max_digits=12,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    class Meta:
        model = Amortization
        fields = [
            "accrued_journal_entry_item",
            "periods",
            "description",
            "suggested_account",
            "salvage_value",
        ]

    def clean_periods(self):
        periods = self.cleaned_data["periods"]

        if periods < 1:
            raise ValidationError("Periods must be >= 1")

        return periods

    def clean(self):
        cleaned = super().clean()
        salvage = cleaned.get("salvage_value")
        jei = cleaned.get("accrued_journal_entry_item")

        if salvage is not None and jei is not None and salvage >= abs(jei.amount):
            self.add_error(
                "salvage_value", "Salvage value must be less than asset cost."
            )

        return cleaned

    def save(self, commit=True):
        instance = super(AmortizationForm, self).save(commit=False)
        journal_entry_item = self.cleaned_data["accrued_journal_entry_item"]
        instance.amount = abs(journal_entry_item.amount)
        instance.entity = journal_entry_item.entity

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
    tax_type = forms.ModelChoiceField(
        required=False,
        queryset=get_tax_accounts(),
    )

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
            queryset = queryset.filter(
                transaction__account=self.cleaned_data["tax_type"]
            )

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
        fields = ["account", "date", "amount"]

    def __init__(self, *args, **kwargs):
        super(TaxChargeForm, self).__init__(*args, **kwargs)
        last_days_of_month_tuples = utils.get_last_days_of_month_tuples()
        self.fields["date"].choices = last_days_of_month_tuples
        last_day_of_last_month = last_days_of_month_tuples[0][0]
        self.fields["date"].initial = last_day_of_last_month
        self.fields["account"].queryset = get_tax_accounts()


class TransactionLinkForm(forms.Form):
    first_transaction = forms.ModelChoiceField(
        queryset=Transaction.objects.select_related("account__entity"),
        required=True,
        label="Base Transaction",
        widget=forms.HiddenInput(),
    )
    second_transaction = forms.ModelChoiceField(
        queryset=Transaction.objects.select_related("account__entity"),
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
                instance = form.save(journal_entry, type, commit=commit)
                instances.append(instance)

        return instances


class JournalEntryItemForm(forms.ModelForm):
    amount = CommaDecimalField(
        required=False,
        initial=0.00,
        decimal_places=2,
        max_digits=12,
        validators=[MinValueValidator(Decimal("0.00"))],
        widget=forms.NumberInput(attrs={"step": "0.01"}),
    )
    account = forms.CharField(required=False)
    entity = forms.CharField(required=False)

    class Meta:
        model = JournalEntryItem
        fields = ("account", "amount", "entity")

    def __init__(
        self,
        *args,
        open_accounts_choices: Dict[str, int],
        open_entities_choices: Dict[str, int],
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.open_accounts_choices = open_accounts_choices
        self.open_entities_choices = open_entities_choices

        # Use the passed in choices for a field's choices, for example:
        self.fields["account"].choices = [
            key for key in self.open_accounts_choices.keys()
        ]
        self.fields["entity"].choices = [
            key for key in self.open_entities_choices.keys()
        ]

        # If the JEI already exists, need to fill in the name for the datalist
        if self.instance.pk:
            journal_entry_item = JournalEntryItem.objects.select_related(
                "account", "entity"
            ).get(pk=self.instance.pk)
            self.account_name = journal_entry_item.account.name
            try:
                self.entity_name = journal_entry_item.entity.name
            except AttributeError:
                pass

    def clean_account(self):
        account_name = self.cleaned_data.get("account", "")
        if not account_name:
            return None
        account = self.open_accounts_choices.get(account_name, None)
        if account:
            return account
        else:
            raise forms.ValidationError("This Account does not exist.")

    def clean_entity(self):
        entity_name = self.cleaned_data.get("entity", "")
        if not entity_name:
            return None
        entity = self.open_entities_choices.get(entity_name, None)
        if not entity:
            entity = Entity.objects.create(name=entity_name)
            self.created_entity = entity

        return entity

    def clean(self):
        cleaned_data = super().clean()
        account = cleaned_data.get("account")
        amount = cleaned_data.get("amount")
        entity = cleaned_data.get("entity")

        # If all fields are empty, this is a blank row to be skipped
        if not account and not amount and not entity:
            return cleaned_data

        # If partially filled, add errors to specific fields
        if not account:
            self.add_error("account", "This field is required.")
        if not amount:
            self.add_error("amount", "This field is required.")
        if not entity:
            self.add_error("entity", "This field is required.")

        return cleaned_data

    def save(self, journal_entry, type, commit=True):
        instance = super(JournalEntryItemForm, self).save(commit=False)

        instance.journal_entry = journal_entry
        instance.type = type
        if commit:
            instance.save()

        return instance


IS_CLOSED_CHOICES = (
    (None, "---------"),
    (True, "True"),
    (False, "False"),
)


class BaseFilterForm(forms.Form):
    """Shared filter fields for transaction search/filter forms."""
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)
    account = forms.ModelMultipleChoiceField(
        queryset=Account.objects.all(), required=False
    )
    transaction_type = forms.MultipleChoiceField(
        choices=Transaction.TransactionType.choices, required=False
    )
    related_account = forms.ModelMultipleChoiceField(
        queryset=Account.objects.all(), required=False
    )


class TransactionFilterForm(BaseFilterForm):
    is_closed = forms.ChoiceField(required=False, choices=IS_CLOSED_CHOICES)
    LINKED_TRANSACTION_CHOICES = (
        (None, "---------"),
        (True, "Linked"),
        (False, "Unlinked"),
    )
    has_linked_transaction = forms.ChoiceField(
        required=False, choices=LINKED_TRANSACTION_CHOICES
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


class AccountForm(forms.ModelForm):
    """User-facing form for creating/editing accounts via the Settings page.

    Exposes a curated subset of fields. System-managed fields (special_type,
    tax_payable_account, tax_rate, tax_amount) are intentionally hidden so users
    can't corrupt tax/statement behavior.
    """

    entity = forms.ModelChoiceField(
        queryset=Entity.objects.all().order_by("name"),
        required=False,
    )
    csv_profile = forms.ModelChoiceField(
        queryset=CSVProfile.objects.all().order_by("name"),
        required=False,
    )

    class Meta:
        model = Account
        fields = [
            "name",
            "type",
            "sub_type",
            "entity",
            "csv_profile",
            "is_closed",
            "is_depreciation",
        ]

    def clean(self):
        cleaned_data = super().clean()
        account_type = cleaned_data.get("type")
        sub_type = cleaned_data.get("sub_type")

        # Validate that the chosen sub_type is valid for the chosen type.
        if account_type and sub_type:
            valid_sub_types = Account.SUBTYPE_TO_TYPE_MAP.get(account_type, [])
            if sub_type not in valid_sub_types:
                self.add_error(
                    "sub_type",
                    f"'{sub_type}' is not a valid sub-type for {account_type} accounts.",
                )

        return cleaned_data


class EntityForm(forms.ModelForm):
    """User-facing form for creating/editing entities via the Settings page.

    The model's ``unique=True`` on ``name`` gives duplicate-name validation for
    free (surfaced on the ``name`` field during ``is_valid()``).
    """

    class Meta:
        model = Entity
        fields = ["name", "is_closed"]


class PrefillForm(forms.ModelForm):
    """User-facing form for creating/editing prefills via the Settings page.

    A prefill is a named template; Doc Searches (and Prefill Items) hang off it.
    Mirrors ``EntityForm``.
    """

    class Meta:
        model = Prefill
        fields = ["name", "is_closed"]


class DocSearchForm(forms.ModelForm):
    """User-facing form for creating/editing a prefill's Doc Searches.

    ``prefill`` is intentionally excluded — the view/service scopes each Doc
    Search to its parent prefill. The either/or field rules (keyword vs
    table row/column; account+type vs selection) are not re-implemented here:
    ``ModelForm._post_clean`` calls ``DocSearch.clean()`` (api/models.py), so
    those surface as ``non_field_errors`` automatically.
    """

    account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_closed=False).order_by("name"),
        required=False,
    )
    entity = forms.ModelChoiceField(
        queryset=Entity.objects.all().order_by("name"),
        required=False,
    )

    class Meta:
        model = DocSearch
        fields = [
            "keyword",
            "table_name",
            "row",
            "column",
            "account",
            "journal_entry_item_type",
            "selection",
            "entity",
        ]


class AutoTagForm(forms.ModelForm):
    """User-facing form for creating/editing autotags via the Settings page.

    An autotag is a rule: when ``search_string`` appears (case-insensitively) in
    an incoming transaction's description, the transaction is pre-filled with the
    tag's account/entity/prefill and transaction type. Only ``search_string`` is
    required; the target fields are optional. Mirrors ``UtilityBillRuleForm``.
    """

    account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_closed=False).order_by("name"),
        required=False,
    )
    prefill = forms.ModelChoiceField(
        queryset=Prefill.objects.filter(is_closed=False).order_by("name"),
        required=False,
    )
    entity = forms.ModelChoiceField(
        queryset=Entity.objects.all().order_by("name"),
        required=False,
    )

    class Meta:
        model = AutoTag
        fields = [
            "search_string",
            "account",
            "transaction_type",
            "prefill",
            "entity",
        ]


class UtilityBillRuleForm(forms.ModelForm):
    """User-facing form for creating/editing utility-bill rules via Settings.

    A rule maps a utility account number (extracted from the bill email) to the
    ledger account a matching bank transaction should be tagged with.
    """

    account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_closed=False).order_by("name"),
    )
    entity = forms.ModelChoiceField(
        queryset=Entity.objects.all().order_by("name"),
        required=False,
    )

    class Meta:
        model = UtilityBillRule
        fields = [
            "from_address",
            "subject",
            "account_number",
            "address_hint",
            "transaction_description_match",
            "account",
            "entity",
            "transaction_type",
        ]


class LoanForm(forms.ModelForm):
    """User-facing form for creating/editing a loan via Settings.

    Saving (re)generates the amortization schedule in the service layer. The
    principal account must be a LIABILITY and the interest account an EXPENSE;
    the optional payment account scopes which transactions can auto-match.
    """

    original_amount = CommaDecimalField(
        decimal_places=2,
        max_digits=12,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    annual_interest_rate = CommaDecimalField(
        decimal_places=4,
        max_digits=6,
        validators=[MinValueValidator(Decimal("0"))],
    )
    payment_amount = CommaDecimalField(
        required=False,
        decimal_places=2,
        max_digits=12,
    )
    principal_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(
            type=Account.Type.LIABILITY, is_closed=False
        ).order_by("name"),
    )
    interest_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(
            type=Account.Type.EXPENSE, is_closed=False
        ).order_by("name"),
    )
    payment_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_closed=False).order_by("name"),
        required=False,
    )
    entity = forms.ModelChoiceField(
        queryset=Entity.objects.all().order_by("name"),
        required=False,
    )

    class Meta:
        model = Loan
        fields = [
            "name",
            "original_amount",
            "annual_interest_rate",
            "term_months",
            "start_date",
            "payment_amount",
            "principal_account",
            "interest_account",
            "payment_account",
            "description_match",
            "date_window_days",
            "entity",
        ]

    def clean_term_months(self):
        term_months = self.cleaned_data["term_months"]
        if term_months < 1:
            raise ValidationError("Term must be at least 1 month.")
        return term_months


class RecharacterizeOperationForm(forms.Form):
    """Field-level cleaning for a manually built recharacterize operation.

    Choices are constrained to real account/entity names; semantic guardrails
    (swap-blocked accounts, type match, empty filter) are intentionally left to
    recharacterize_services._evaluate_operation, which surfaces them as a blocked
    operation in the preview — identical to an agent-proposed op. The form only
    normalizes types (dates) and constrains choices.
    """

    ENTRY_TYPE_CHOICES = [("", "Any"), ("debit", "Debit"), ("credit", "Credit")]
    ACTION_CHOICES = [
        ("view", "View matching items (no change)"),
        ("set_entity", "Set entity"),
        ("clear_entity", "Clear entity"),
        ("change_account", "Change account"),
    ]

    # Widget attrs live on the fields (not hand-written in the template) so the
    # builder renders each field with ``{{ manual_form.<field> }}`` and prefill
    # from ``initial`` (when editing an op) "just works" with no template logic.
    description_contains = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "input", "placeholder": "e.g. coffee"}),
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "input", "type": "date"}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "input", "type": "date"}),
    )
    # account/entity are multi-select filters (match any of the chosen) rendered
    # with the shared typeahead-multiselect component. ``initial=list`` keeps an
    # unbound field's value an empty list so that component renders cleanly.
    account = forms.ModelMultipleChoiceField(
        queryset=Account.objects.all().order_by("name"), required=False, initial=list
    )
    entity = forms.ModelMultipleChoiceField(
        queryset=Entity.objects.all().order_by("name"), required=False, initial=list
    )
    entity_is_empty = forms.BooleanField(required=False)
    entry_type = forms.ChoiceField(
        required=False,
        choices=ENTRY_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "select"}),
    )

    action_type = forms.ChoiceField(choices=ACTION_CHOICES)
    target_entity = forms.ChoiceField(
        required=False, choices=[], widget=forms.Select(attrs={"class": "select"})
    )
    to_account = forms.ChoiceField(
        required=False, choices=[], widget=forms.Select(attrs={"class": "select"})
    )

    def __init__(self, *args, catalogs, **kwargs):
        # ``catalogs`` is a required keyword-only arg (a FormCatalogs) so the
        # dependency runs strictly one way: View -> Service and View -> Form. The
        # view builds the catalogs and passes them in; the form never reaches back
        # into the service layer.
        super().__init__(*args, **kwargs)
        # The action targets are single-valued (you set one entity / swap to one
        # account). A blank option lets the _evaluate_operation guard message fire
        # instead of a generic "invalid choice" — the preview explains what's missing.
        self.fields["target_entity"].choices = [("", "—")] + [
            (n, n) for n in catalogs.entities
        ]
        self.fields["to_account"].choices = [("", "—")] + [
            (n, n) for n in catalogs.accounts
        ]
