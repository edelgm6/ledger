from import_export import resources
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget

from .models import Account, JournalEntry, JournalEntryItem, Transaction


class AccountResource(resources.ModelResource):
    class Meta:
        model = Account
        fields = ("id", "name", "type", "sub_type", "system_role", "tax_kind", "is_closed")

    def before_import_row(self, row, **kwargs):
        # Blank role/kind cells import as NULL rather than empty strings.
        for column in ("system_role", "tax_kind"):
            if column in row and not row[column].strip():
                row[column] = None


class JournalEntryItemResource(resources.ModelResource):
    journal_entry = Field(
        column_name="journal_entry",
        attribute="journal_entry",
        widget=ForeignKeyWidget(JournalEntry, "id"),
    )

    class Meta:
        model = JournalEntryItem
        fields = ("id", "journal_entry", "type", "amount", "account")


class JournalEntryResource(resources.ModelResource):
    transaction = Field(
        column_name="transaction",
        attribute="transaction",
        widget=ForeignKeyWidget(Transaction, "id"),
    )

    class Meta:
        model = JournalEntry
        fields = ("id", "date", "description", "transaction")
        export_order = ("id", "date", "description", "transaction")


class TransactionResource(resources.ModelResource):
    class Meta:
        model = Transaction
        fields = (
            "id",
            "date",
            "account",
            "amount",
            "description",
            "category",
            "is_closed",
            "linked_transaction",
        )
