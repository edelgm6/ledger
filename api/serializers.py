from datetime import date
from rest_framework import serializers
from api.models import Transaction, Account, JournalEntry, JournalEntryItem, CSVProfile, AutoTag, Reconciliation, TaxCharge
from api import helpers
from api.statement import BalanceSheet, IncomeStatement

class ReconciliationsCreateSerializer(serializers.Serializer):
    date = serializers.DateField()

    def validate_date(self, value):

        if not helpers.is_last_day_of_month(value):
            raise serializers.ValidationError('Must be last day of month')
        return value

    def create(self, validated_data):
        date = validated_data['date']

        balance_sheet_accounts = Account.objects.filter(type__in=[Account.Type.ASSET,Account.Type.LIABILITY])
        reconciliation_list = []
        for account in balance_sheet_accounts:
            reconciliation_list.append(
                Reconciliation(
                    account=account,
                    date=date
                )
            )

        reconciliations = Reconciliation.objects.bulk_create(reconciliation_list)
        return reconciliations

# Following guide here: https://www.django-rest-framework.org/api-guide/serializers/#customizing-multiple-update
class TaxChargeListSerializer(serializers.ListSerializer):

    def update(self, instance, validated_data):
        # Maps for id->instance and id->data item.
        reconciliation_mapping = {reconciliation.id: reconciliation for reconciliation in instance}
        data_mapping = {item['id']: item for item in validated_data}

        # Perform creations and updates.
        reconciliations_list = []
        for reconciliation_id, data in data_mapping.items():
            reconciliation = reconciliation_mapping.get(reconciliation_id, None)
            reconciliations_list.append(self.child.update(reconciliation, data))

        return reconciliations_list

class ReconciliationInputSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField()

    class Meta:
        model = Reconciliation
        fields = '__all__'
        depth = 1
        list_serializer_class = TaxChargeListSerializer

class ReconciliationOutputSerializer(serializers.ModelSerializer):
    current_balance = serializers.SerializerMethodField()

    class Meta:
        model = Reconciliation
        fields = '__all__'
        depth = 1

    def get_current_balance(self, reconciliation):
        balance_sheet = BalanceSheet(reconciliation.date)
        balance = balance_sheet.get_balance(reconciliation.account)
        return balance

class CSVProfileOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = CSVProfile
        fields = ['name','date','amount','description','category','accounts','account']
        depth = 1

class BalanceOutputSerializer(serializers.Serializer):
    account = serializers.CharField(max_length=200)
    amount = serializers.DecimalField(max_digits=12,decimal_places=2)
    account_type = serializers.CharField(max_length=200)
    account_sub_type = serializers.CharField(max_length=200)
    date = serializers.DateField()
    type = serializers.CharField(max_length=5)

class MetricsOutputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    value = serializers.DecimalField(max_digits=12,decimal_places=2)
    metric_type = serializers.CharField(max_length=200)

class StatementOutputSerializer(serializers.Serializer):
    balances = BalanceOutputSerializer(many=True, read_only=True)
    metrics = MetricsOutputSerializer(many=True, read_only=True)
    summaries = MetricsOutputSerializer(many=True, read_only=True)

class AccountBalanceOutputSerializer(serializers.Serializer):
    balance_sheet = StatementOutputSerializer()
    income_statement = StatementOutputSerializer()
    cash_flow_statement = StatementOutputSerializer()

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

        journal_entry.transaction.close(date.today())
        if transaction_type:
            journal_entry.transaction.type = transaction_type
            journal_entry.transaction.save()

        for journal_entry_item_data in journal_entry_items_data:
            JournalEntryItem.objects.create(journal_entry=journal_entry, **journal_entry_item_data)

        return journal_entry

    def update(self, instance, validated_data):
        journal_entry_items_data = validated_data.pop('journal_entry_items')
        transaction_type = validated_data.pop('transaction_type', None)

        if transaction_type:
            instance.transaction.type = transaction_type
            instance.transaction.save()

        instance.date = validated_data.get('date', instance.date)
        instance.description = validated_data.get('description', instance.description)
        instance.save()

        existing_journal_entry_items = JournalEntryItem.objects.filter(journal_entry=instance)
        existing_journal_entry_items.delete()

        for journal_entry_item_data in journal_entry_items_data:
            JournalEntryItem.objects.create(journal_entry=instance, **journal_entry_item_data)

        return instance

class JournalEntryOutputSerializer(serializers.ModelSerializer):
    journal_entry_items = JournalEntryItemOutputSerializer(many=True, read_only=True)

    class Meta:
        model = JournalEntry
        fields = ['id','date','description','journal_entry_items']
        depth = 1

class AccountOutputSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = '__all__'
        depth = 1

class TransactionTypeOutputSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=200)
    label = serializers.CharField(max_length=200)

class TransactionOutputSerializer(serializers.ModelSerializer):
    journal_entry = JournalEntryOutputSerializer()

    class Meta:
        model = Transaction
        fields = ['id','date','account','amount','description','category','is_closed','date_closed','suggested_account','type','linked_transaction','journal_entry']
        depth = 3

class TransactionInputSerializer(serializers.ModelSerializer):
    account = serializers.SlugRelatedField(queryset=Account.objects.all(),slug_field='name',required=False)
    type = serializers.CharField(max_length=25,required=False)
    linked_transaction = serializers.PrimaryKeyRelatedField(required=False,queryset=Transaction.objects.all())
    is_closed = serializers.BooleanField(required=False)
    suggested_account = serializers.SlugRelatedField(queryset=Account.objects.all(),slug_field='name',required=False)

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
            'suggested_account'
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
        validated_data['type'] = suggested_type
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

class CreateTaxChargeInputSerializer(serializers.ModelSerializer):

    class Meta:
        model = TaxCharge
        fields = ['type', 'amount', 'date']

class TaxChargeInputSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField()

    class Meta:
        model = TaxCharge
        fields = '__all__'
        depth = 1
        list_serializer_class = TaxChargeListSerializer

class TaxChargeOutputSerializer(serializers.ModelSerializer):
    taxable_income = serializers.SerializerMethodField()

    class Meta:
        model = TaxCharge
        fields = ['id','type','transaction','date','amount','taxable_income']
        depth = 1

    def get_taxable_income(self, tax_charge):
        start_date = tax_charge.date.replace(day=1)
        income_statement = IncomeStatement(end_date=tax_charge.date,start_date=start_date)

        return income_statement.get_taxable_income()