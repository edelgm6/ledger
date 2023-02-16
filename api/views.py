from django.shortcuts import render
from django.views import View
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.db.models import Sum
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
        # TODO: Should have a topline account type for balance sheet or income statement
        income_statement_accounts = JournalEntryItem.objects.filter(account__type__in=['income','expense'],journal_entry__date__gte=start_date,journal_entry__date__lte=end_date).values('account__name','account__type','type').annotate(total=Sum('amount'))
        balance_sheet_accounts = JournalEntryItem.objects.filter(account__type__in=['asset','liability','equity']).values('account__name','account__type','type').annotate(total=Sum('amount'))

        # TODO: Turn all of this logic into something that is done in a helper function
        account_balances = {}
        account_groups = [income_statement_accounts,balance_sheet_accounts]
        for account_group in account_groups:
            for entry in account_group:
                account_name = entry['account__name']
                account_type = entry['account__type']
                journal_entry_type = entry['type']
                if not account_balances.get(account_name):
                    account_balances[account_name] = {
                        'type': account_type,
                        'debits': 0,
                        'credits': 0
                    }
                if journal_entry_type == 'credit':
                    account_balances[account_name]['credits'] = entry['total']
                elif journal_entry_type == 'debit':
                    account_balances[account_name]['debits'] = entry['total']

        account_balance_list = []
        for key, value in account_balances.items():
            balance = 0
            if value['type'] in ('asset','expense'):
                balance = value['debits'] - value['credits']
            else:
                balance = value['credits'] - value['debits']

            account_balance_list.append({'account': key, 'balance': balance})

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