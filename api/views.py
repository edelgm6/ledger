from decimal import Decimal
from django.http import Http404
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status, generics
from api.serializers import TransactionOutputSerializer, JournalEntryInputSerializer, JournalEntryOutputSerializer, AccountOutputSerializer, TransactionInputSerializer, AccountBalanceOutputSerializer, TransactionTypeOutputSerializer, CSVProfileOutputSerializer
from api.models import Transaction, Account, CSVProfile
from api import helpers

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

        account_balance_list = helpers.get_account_balances(start_date,end_date)
        account_balance_output_serializer = AccountBalanceOutputSerializer(account_balance_list, many=True)
        return Response(account_balance_output_serializer.data)

class AccountView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        accounts = Account.objects.all().order_by('name')
        account_output_serializer = AccountOutputSerializer(accounts,many=True)
        return Response(account_output_serializer.data)

# TODO: Update this endpoint to take a single blob — will require changing retool to insert the account
# into the transactions blog instead of sending separately
class UploadTransactionsView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        transaction_input_serializer = TransactionInputSerializer(data=request.data, many=True)
        if transaction_input_serializer.is_valid():
            transactions = transaction_input_serializer.save()
            transaction_output_serializer = TransactionOutputSerializer(transactions,many=True)
            return Response(transaction_output_serializer.data, status=status.HTTP_201_CREATED)

        return Response(transaction_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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

    def post(self, request, *args, **kwargs):

        journal_entry_input_serializer = JournalEntryInputSerializer(data=request.data)

        if journal_entry_input_serializer.is_valid():
            journal_entry = journal_entry_input_serializer.save()
            journal_entry_output_serializer = JournalEntryOutputSerializer(journal_entry)
            return Response(journal_entry_output_serializer.data, status=status.HTTP_201_CREATED)

        return Response(journal_entry_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)