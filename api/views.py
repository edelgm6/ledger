import datetime
from decimal import Decimal
from django.http import Http404
from django.views import View
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status, generics
from rest_framework.exceptions import ValidationError
from api.serializers import TransactionOutputSerializer, JournalEntryInputSerializer, JournalEntryOutputSerializer, AccountOutputSerializer, TransactionInputSerializer, AccountBalanceOutputSerializer, TransactionTypeOutputSerializer, CSVProfileOutputSerializer, ReconciliationsCreateSerializer, ReconciliationOutputSerializer, ReconciliationInputSerializer, TaxChargeInputSerializer, TaxChargeOutputSerializer, CreateTaxChargeInputSerializer, BalanceOutputSerializer, TransactionBulkUploadSerializer
from api.models import TaxCharge, Transaction, Account, CSVProfile, Reconciliation, JournalEntry
from api.statement import BalanceSheet, IncomeStatement, CashFlowStatement, Trend

class TrendView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        trend = Trend(start_date,end_date)

        balances_output_serializer = BalanceOutputSerializer(trend.get_balances(), many=True)
        return Response(balances_output_serializer.data)

class PlugReconciliationView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_reconciliation(self, pk):
        try:
            return Reconciliation.objects.get(pk=pk)
        except Reconciliation.DoesNotExist:
            raise Http404

    def put(self, request, pk, format=None):
        reconciliation = self.get_reconciliation(pk)
        journal_entry = reconciliation.plug_investment_change()
        journal_entry_output_serializer = JournalEntryOutputSerializer(journal_entry)
        return Response(journal_entry_output_serializer.data)

class ReconciliationView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        dates = self.request.query_params.getlist('date')

        reconciliations = Reconciliation.objects.filter(date__in=dates).order_by('account__name')
        reconciliation_output_serializer = ReconciliationOutputSerializer(reconciliations, many=True)
        return Response(reconciliation_output_serializer.data)

    def put(self, request, format=None):
        reconciliation_input_serializer = ReconciliationInputSerializer(Reconciliation.objects.all().order_by('account__name'), data=request.data, many=True, partial=True)
        if reconciliation_input_serializer.is_valid():
            reconciliations = reconciliation_input_serializer.save()
            reconciliation_output_serializer = ReconciliationOutputSerializer(reconciliations, many=True)
            return Response(reconciliation_output_serializer.data)
        return Response(reconciliation_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class GenerateReconciliationsView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        reconciliations_create_serializer = ReconciliationsCreateSerializer(data=request.data)
        if reconciliations_create_serializer.is_valid():
            reconciliations = reconciliations_create_serializer.save()
            reconciliation_output_serializer = ReconciliationOutputSerializer(reconciliations, many=True)
            return Response(reconciliation_output_serializer.data)

        return Response(reconciliations_create_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CSVProfileView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        csv_profiles = CSVProfile.objects.all()
        csv_profile_output_serializer = CSVProfileOutputSerializer(csv_profiles, many=True)
        return Response(csv_profile_output_serializer.data)

class TransactionTypeView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        transaction_types = Transaction.TransactionType.choices
        transaction_types_list = []
        for transaction_type in transaction_types:
            transaction_types_list.append({'id': transaction_type[0], 'label': transaction_type[1]})
        transaction_type_serializer = TransactionTypeOutputSerializer(transaction_types_list, many=True)
        return Response(transaction_type_serializer.data)

class AccountBalanceView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        income_statement = IncomeStatement(end_date=end_date,start_date=start_date)
        balance_sheet = BalanceSheet(end_date=end_date)

        balance_sheet_start_date = datetime.date.fromisoformat(start_date) - datetime.timedelta(days=1)
        balance_sheet_start = BalanceSheet(end_date=balance_sheet_start_date)
        cash_flow_statement = CashFlowStatement(income_statement,balance_sheet_start,balance_sheet)
        statements = {
            'income_statement': income_statement,
            'balance_sheet': balance_sheet,
            'cash_flow_statement': cash_flow_statement
        }

        account_balance_output_serializer = AccountBalanceOutputSerializer(statements)
        return Response(account_balance_output_serializer.data)

class AccountView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        accounts = Account.objects.all().order_by('name')

        csv_only = self.request.query_params.get('csv_only')
        if csv_only:
            accounts = accounts.exclude(csv_profile__isnull=bool(csv_only))

        account_output_serializer = AccountOutputSerializer(accounts,many=True)
        return Response(account_output_serializer.data)

# TODO: Update this endpoint to take a single blob — will require changing retool to insert the account
# into the transactions blog instead of sending separately
class UploadTransactionsView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        transaction_input_serializer = TransactionBulkUploadSerializer(data=request.data)
        if transaction_input_serializer.is_valid():
            print(transaction_input_serializer.data['account'])
            account = Account.objects.get(name=transaction_input_serializer.data['account'])
            csv_profile = account.csv_profile
            transactions = csv_profile.create_transactions_from_csv(transaction_input_serializer.data['blob'], account)
            transaction_output_serializer = TransactionOutputSerializer(transactions,many=True)
            return Response(transaction_output_serializer.data, status=status.HTTP_201_CREATED)

        return Response(transaction_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TaxChargeView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_tax_charge(self, pk):
        try:
            return TaxCharge.objects.get(pk=pk)
        except TaxCharge.DoesNotExist:
            raise Http404

    def get(self, request, *args, **kwargs):
        tax_charges = TaxCharge.objects.all().order_by('date')

        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        type = self.request.query_params.get('type')
        if start_date:
            tax_charges = tax_charges.filter(date__gte=start_date)
        if end_date:
            tax_charges = tax_charges.filter(date__lte=end_date)
        if type:
            tax_charges = tax_charges.filter(type=type)

        tax_charge_output_serializer = TaxChargeOutputSerializer(tax_charges,many=True)
        return Response(tax_charge_output_serializer.data)

    def put(self, request, format=None):
        tax_charge_input_serializer = TaxChargeInputSerializer(TaxCharge.objects.all().order_by('date'), data=request.data, many=True, partial=True)
        if tax_charge_input_serializer.is_valid():
            tax_charges = tax_charge_input_serializer.save()
            tax_charge_output_serializer = TaxChargeOutputSerializer(tax_charges, many=True)
            return Response(tax_charge_output_serializer.data)
        return Response(tax_charge_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        tax_charge_input_serializer = CreateTaxChargeInputSerializer(data=request.data)
        if tax_charge_input_serializer.is_valid():
            tax_charge = tax_charge_input_serializer.save()
            tax_charge_output_serializer = TaxChargeOutputSerializer(tax_charge)
            return Response(tax_charge_output_serializer.data, status=status.HTTP_201_CREATED)

        return Response(tax_charge_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TransactionView(generics.ListAPIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionOutputSerializer

    def get_transaction(self, pk):
        try:
            return Transaction.objects.get(pk=pk)
        except Transaction.DoesNotExist:
            raise Http404

    def get_queryset(self):
        queryset = Transaction.objects.all()
        is_closed = self.request.query_params.get('is_closed')
        include_types = self.request.query_params.getlist('include_type')
        exclude_types = self.request.query_params.getlist('exclude_type')
        has_linked_transaction = self.request.query_params.get('has_linked_transaction')
        accounts = self.request.query_params.getlist('account')
        amount = self.request.query_params.get('amount')
        account_sub_types = self.request.query_params.getlist('account_sub_type')
        journal_entry_item_account_sub_types = self.request.query_params.getlist('journal_entry_item_account_sub_type')
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        is_tax_charge = self.request.query_params.get('is_tax_charge')
        related_accounts = self.request.query_params.getlist('related_account')

        if is_closed:
            queryset = queryset.filter(is_closed=is_closed)
        if include_types:
            queryset = queryset.filter(type__in=include_types)
        if exclude_types:
            queryset = queryset.exclude(type__in=exclude_types)
        if has_linked_transaction:
            null_filter = has_linked_transaction.lower() != 'true'
            queryset = queryset.filter(linked_transaction__isnull=null_filter)
        if accounts:
            queryset = queryset.filter(account__name__in=accounts)
        if amount:
            queryset = queryset.filter(amount__in=[Decimal(amount), -Decimal(amount)])
        if account_sub_types:
            queryset = queryset.filter(account__sub_type__in=account_sub_types)
        if journal_entry_item_account_sub_types:
            queryset = queryset.filter(journal_entry__journal_entry_items__account__sub_type__in=journal_entry_item_account_sub_types)
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)
        if is_tax_charge:
            queryset = queryset.filter(tax_charge=is_tax_charge)
        if related_accounts:
            queryset = queryset.filter(journal_entry__journal_entry_items__account__name__in=related_accounts)

        queryset = queryset.order_by('date','account','description')
        return queryset

    def post(self, request, *args, **kwargs):
        transaction_input_serializer = TransactionInputSerializer(data=request.data)
        if transaction_input_serializer.is_valid():
            transaction = transaction_input_serializer.save()
            transaction_output_serializer = TransactionOutputSerializer(transaction)
            return Response(transaction_output_serializer.data, status=status.HTTP_201_CREATED)
        return Response(transaction_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk, format=None):
        transaction = self.get_transaction(pk)
        transaction_input_serializer = TransactionInputSerializer(transaction, data=request.data, partial=True)
        if transaction_input_serializer.is_valid():
            transaction = transaction_input_serializer.save()
            transaction_output_serializer = TransactionOutputSerializer(transaction)
            return Response(transaction_output_serializer.data)
        return Response(transaction_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class JournalEntryView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get_journal_entry(self, pk):
        try:
            return JournalEntry.objects.get(pk=pk)
        except JournalEntry.DoesNotExist:
            raise Http404

    def post(self, request, *args, **kwargs):

        journal_entry_input_serializer = JournalEntryInputSerializer(data=request.data)

        if journal_entry_input_serializer.is_valid():
            journal_entry = journal_entry_input_serializer.save()
            journal_entry_output_serializer = JournalEntryOutputSerializer(journal_entry)
            return Response(journal_entry_output_serializer.data, status=status.HTTP_201_CREATED)

        return Response(journal_entry_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, *args, **kwargs):
        sub_types = self.request.query_params.getlist('sub_type')
        journal_entries = JournalEntry.objects.all().order_by('date')

        if sub_types:
            journal_entries.filter(journal_entry_items__account__sub_type__in=sub_types)
        journal_entry_output_serializer = JournalEntryOutputSerializer(journal_entries, many=True)
        return Response(journal_entry_output_serializer.data)

    def put(self, request, pk, format=None):
        journal_entry = self.get_journal_entry(pk)
        journal_entry_input_serializer = JournalEntryInputSerializer(journal_entry, data=request.data, partial=True)

        if journal_entry_input_serializer.is_valid():
            journal_entry = journal_entry_input_serializer.save()
            journal_entry_output_serializer = JournalEntryOutputSerializer(journal_entry)
            return Response(journal_entry_output_serializer.data, status=status.HTTP_201_CREATED)

        return Response(journal_entry_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)