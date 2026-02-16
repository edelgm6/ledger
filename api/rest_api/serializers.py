from decimal import Decimal

from rest_framework import serializers

from api.models import Account, Entity, Transaction


class TransactionSerializer(serializers.ModelSerializer):
    account = serializers.CharField(source="account.name")
    suggested_account = serializers.SerializerMethodField()
    journal_entry_id = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            "id",
            "date",
            "account",
            "amount",
            "description",
            "category",
            "is_closed",
            "date_closed",
            "type",
            "suggested_account",
            "journal_entry_id",
        ]

    def get_suggested_account(self, obj) -> str | None:
        return obj.suggested_account.name if obj.suggested_account else None

    def get_journal_entry_id(self, obj) -> int | None:
        journal_entry = getattr(obj, "journal_entry", None)
        return journal_entry.id if journal_entry else None


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["id", "name", "type", "sub_type", "is_closed"]


class EntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Entity
        fields = ["id", "name", "is_closed"]


class JournalEntryItemInputSerializer(serializers.Serializer):
    account = serializers.CharField(max_length=200)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    entity = serializers.CharField(max_length=200, required=False, allow_blank=True)


class JournalEntryInputSerializer(serializers.Serializer):
    transaction_id = serializers.IntegerField()
    debits = JournalEntryItemInputSerializer(many=True, min_length=1)
    credits = JournalEntryItemInputSerializer(many=True, min_length=1)
    created_by = serializers.CharField(max_length=100, default="user")


class BulkJournalEntryInputSerializer(serializers.Serializer):
    journal_entries = JournalEntryInputSerializer(many=True, min_length=1)
