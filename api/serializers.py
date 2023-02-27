import csv
import io
from datetime import datetime, date
from rest_framework import serializers
from api.models import Transaction, Account, JournalEntry, JournalEntryItem, CSVProfile, AutoTag

class CSVProfileOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = CSVProfile
        fields = ['name','date','amount','description','category','accounts','account']
        depth = 1

class AccountBalanceOutputSerializer(serializers.Serializer):
    account = serializers.CharField(max_length=200)
    balance = serializers.DecimalField(max_digits=12,decimal_places=2)

class JournalEntryItemInputSerializer(serializers.ModelSerializer):
    account = serializers.SlugRelatedField(queryset=Account.objects.all(),slug_field='name')

    class Meta:
        model = JournalEntryItem
        fields = ['type','amount','account']

class JournalEntryItemOutputSerializer(serializers.ModelSerializer):
    account = serializers.SlugRelatedField(queryset=Account.objects.all(),slug_field='name')

    class Meta:
        model = JournalEntryItem
        fields = ['id','type','amount','account']

class JournalEntryInputSerializer(serializers.ModelSerializer):
    transaction = serializers.PrimaryKeyRelatedField(allow_null=True,required=False,queryset=Transaction.objects.all())
    journal_entry_items = JournalEntryItemInputSerializer(many=True)
    transaction_type = serializers.CharField(allow_null=True,required=False)

    class Meta:
        model = JournalEntry
        fields = '__all__'

    def validate_transaction_type(self, value):
        transaction_types = Transaction.TransactionType.values
        if value and value not in transaction_types:
            raise serializers.ValidationError('Transaction Type not valid')

        return value

    def validate(self, data):
        journal_entry_items = data['journal_entry_items']
        debits = 0
        credits = 0
        for journal_entry_item in journal_entry_items:
            amount = journal_entry_item['amount']
            type = journal_entry_item['type']

            if type == 'debit':
                debits += amount
            elif type == 'credit':
                credits += amount

        if debits != credits:
            raise serializers.ValidationError(
                'Debits and Credits not equal \n' +
                'Debits = ' + str(debits) + '\n'
                'Credits = ' + str(credits) + '\n'
                )

        if data.get('transaction'):
            transaction = data['transaction']
            transaction_amount = abs(transaction.amount)
            journal_entry_amounts = [journal_entry_item['amount'] for journal_entry_item in journal_entry_items]
            if transaction_amount not in journal_entry_amounts:
                raise serializers.ValidationError('If connecting to a transactions, at least one journal entry item must equal the transaction amount.')

        return data

    def create(self, validated_data):
        journal_entry_items_data = validated_data.pop('journal_entry_items')
        transaction_type = validated_data.pop('transaction_type', None)
        journal_entry = JournalEntry.objects.create(**validated_data)

        if journal_entry.transaction:
            journal_entry.transaction.close(date.today())
            if transaction_type:
                journal_entry.transaction.type = transaction_type
                journal_entry.transaction.save()

        for journal_entry_item_data in journal_entry_items_data:
            JournalEntryItem.objects.create(journal_entry=journal_entry, **journal_entry_item_data)

        return journal_entry

class JournalEntryOutputSerializer(serializers.ModelSerializer):
    journal_entry_items = JournalEntryItemOutputSerializer(many=True, read_only=True)

    class Meta:
        model = JournalEntry
        fields = ['id','date','description','transaction','journal_entry_items']

class AccountOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = '__all__'
        depth = 1

class TransactionTypeOutputSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=200)
    label = serializers.CharField(max_length=200)

class TransactionOutputSerializer(serializers.ModelSerializer):

    class Meta:
        model = Transaction
        fields = '__all__'
        depth = 2

class TransactionInputSerializer(serializers.ModelSerializer):
    account = serializers.SlugRelatedField(queryset=Account.objects.all(),slug_field='name',required=False)
    type = serializers.CharField(max_length=25,required=False)
    linked_transaction = serializers.PrimaryKeyRelatedField(required=False,queryset=Transaction.objects.all())
    is_closed = serializers.BooleanField(required=False)
    suggested_account = serializers.SlugRelatedField(queryset=Account.objects.all(),slug_field='name',required=False)
    suggested_type = serializers.CharField(max_length=25,required=False)

    class Meta:
        model = Transaction
        fields = [
            'date',
            'amount',
            'category',
            'description',
            'account',
            'type',
            'linked_transaction',
            'is_closed',
            'suggested_account',
            'suggested_type'
        ]

    def create(self, validated_data):
        suggested_account = None
        suggested_type = Transaction.TransactionType.PURCHASE
        auto_tags = AutoTag.objects.all()

        for tag in auto_tags:
            if tag.search_string in validated_data['description'].lower():
                suggested_account = tag.account
                if tag.transaction_type:
                    suggested_type = tag.transaction_type
                break

        validated_data['suggested_account'] = suggested_account
        validated_data['suggested_type'] = suggested_type
        transaction = Transaction.objects.create(**validated_data)

        return transaction

    def update(self, instance, validated_data):
        instance.linked_transaction = validated_data.get('linked_transaction', instance.linked_transaction)
        instance.date = validated_data.get('date', instance.date)
        instance.amount = validated_data.get('amount', instance.amount)
        instance.category = validated_data.get('category', instance.category)
        instance.description = validated_data.get('description', instance.description)
        instance.type = validated_data.get('type', instance.type)

        # TODO: Is there a clean way to always update the date when this field is updated?
        instance.is_closed = validated_data.get('is_closed', instance.is_closed)
        if validated_data.get('is_closed'):
            instance.close(date.today())

        if validated_data.get('linked_transaction'):
            validated_data.get('linked_transaction').close(date.today())
            instance.suggested_account = validated_data.get('linked_transaction').account

        instance.save()

        return instance