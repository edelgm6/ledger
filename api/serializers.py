import csv
import io
from datetime import datetime, date
from rest_framework import serializers
from api.models import Transaction, Account, JournalEntry, JournalEntryItem

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
    journal_entry_items = JournalEntryItemInputSerializer(many=True)

    class Meta:
        model = JournalEntry
        fields = '__all__'

    # Add in a validation first to check that the journal entry
    # items balance debits and credits

    def create(self, validated_data):
        journal_entry_items_data = validated_data.pop('journal_entry_items')
        journal_entry = JournalEntry.objects.create(**validated_data)
        for journal_entry_item_data in journal_entry_items_data:
            print(journal_entry_items_data)
            JournalEntryItem.objects.create(journal_entry=journal_entry, **journal_entry_item_data)

        return journal_entry

class JournalEntryOutputSerializer(serializers.ModelSerializer):
    journal_entry_items = JournalEntryItemOutputSerializer(many=True, read_only=True)

    class Meta:
        model = JournalEntry
        fields = ['id','date','description','transaction','journal_entry_items']

class TransactionOutputSerializer(serializers.ModelSerializer):

    class Meta:
        model = Transaction
        fields = '__all__'

# class TransactionCsvSerializer(serializers.Serializer):
#     file = serializers.FileField()
#     account = serializers.CharField()

#     def validate_file(self, csv_file):
#         print(csv_file.name)
#         if csv_file.name[-4:] != '.csv':
#             raise serializers.ValidationError('File must be CSV')

#         # Add any additional validation logic here

#         return csv_file

#     def validate_account(self, account):
#         # Need to make sure the account is in the list of possible accounts
#         account_names = Account.objects.values_list('name',flat=True)
#         if account not in account_names:
#             raise serializers.ValidationError('Invalid account name')

#         return account

#     def create(self, validated_data):
#         csv_file = validated_data['file']
#         account = Account.objects.get(name=validated_data['account'])

#         file = io.StringIO(csv_file.read().decode('utf-8'))
#         reader = csv.reader(file)
#         headers = next(reader)
#         transactions_list = []
#         for row in reader:
#             date_string = row[0]
#             date_format = "%m/%d/%Y"
#             parsed_date = datetime.strptime(date_string, date_format)
#             only_date = parsed_date.date()

#             transactions_list.append(Transaction(
#                 date=only_date,
#                 account = account,
#                 amount = row[5],
#                 description = row[2],
#                 category = row[3]
#             ))
#         csv_file.close()

#         transactions = Transaction.objects.bulk_create(transactions_list)

#         return transactions
