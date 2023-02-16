from django.shortcuts import render
from django.views import View
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import FileUploadParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status, generics
from api.serializers import TransactionOutputSerializer, JournalEntryInputSerializer, JournalEntryOutputSerializer, AccountOutputSerializer, TransactionUploadSerializer, TransactionInputSerializer, AccountBalanceOutputSerializer
from api.models import Transaction, Account, JournalEntryItem
from api.forms import TransactionsUploadForm
from api.CsvHandler import CsvHandler
from api import helpers

@method_decorator(login_required, name='dispatch')
class Index(View):
    template = 'api/index.html'
    form = TransactionsUploadForm

    def get(self, request, format=None):
        return render(request, self.template, {'form': self.form})

    def post(self, request, format=None):
        whatever = self.form(request.POST, request.FILES)
        if whatever.is_valid():
            print(request.FILES['file'])
            handler = CsvHandler(request.FILES['file'], request.POST['account'])
            handler.create_transactions()
            return HttpResponseRedirect('/')
        else:
            print('invalid')
            return render(request, self.template, {'form': self.form})

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
        accounts = Account.objects.all()
        account_output_serializer = AccountOutputSerializer(accounts,many=True)
        return Response(account_output_serializer.data)

# TODO: Update this endpoint to take a single blob — will require changing retool to insert the account
# into the transactions blog instead of sending separately
class UploadTransactionsView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        transaction_upload_serializer = TransactionUploadSerializer(data=request.data)
        if transaction_upload_serializer.is_valid():
            transactions = transaction_upload_serializer.save()
            transaction_output_serializer = TransactionOutputSerializer(transactions,many=True)
            return Response(transaction_output_serializer.data, status=status.HTTP_201_CREATED)

        return Response(transaction_upload_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
        transaction_types = self.request.query_params.getlist('type')
        if is_closed:
            queryset = queryset.filter(is_closed=is_closed)
        if transaction_types:
            queryset = queryset.filter(type__in=transaction_types)

        queryset = queryset.order_by('date','account','description')
        return queryset

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
        else:
            print(journal_entry_input_serializer.errors)
            return Response(journal_entry_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)