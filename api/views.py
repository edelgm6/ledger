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
from api.serializers import TransactionOutputSerializer, JournalEntryInputSerializer, JournalEntryOutputSerializer, AccountOutputSerializer
from api.models import Transaction, Account
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

class AccountView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        accounts = Account.objects.all()
        account_output_serializer = AccountOutputSerializer(accounts,many=True)
        return Response(account_output_serializer.data)

class TransactionView(generics.ListAPIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionOutputSerializer

    def get_queryset(self):
        queryset = Transaction.objects.all()
        is_closed = self.request.query_params.get('is_closed')
        if is_closed:
            queryset = queryset.filter(is_closed=is_closed)
        return queryset


class JournalEntryView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    # def get(self, request, *args, **kwargs):
    #     journal_entries = JournalEntry.objects.all()
    #     print(journal_entries)
    #     journal_entry_output_serializer = JournalEntryOutputSerializer(journal_entries,many=True)
    #     return Response(journal_entry_output_serializer.data)

    def post(self, request, *args, **kwargs):

        journal_entry_input_serializer = JournalEntryInputSerializer(data=request.data)

        if journal_entry_input_serializer.is_valid():
            journal_entry = journal_entry_input_serializer.save()
            journal_entry_output_serializer = JournalEntryOutputSerializer(journal_entry)
            return Response(journal_entry_output_serializer.data, status=status.HTTP_201_CREATED)
        else:
            print(journal_entry_input_serializer.errors)
            return Response(journal_entry_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# class TransactionsUploadView(APIView):
#     parser_class = (FileUploadParser,)

#     def post(self, request, *args, **kwargs):
#         print(request.data)
#         file_serializer = TransactionCsvSerializer(data=request.data)
#         if file_serializer.is_valid():
#             files = file_serializer.save()
#             transactions_output_serializer = TransactionOutputSerializer(files,many=True)
#             return Response(transactions_output_serializer.data, status=status.HTTP_201_CREATED)
#         else:
#             print(file_serializer.errors)
#             return Response(file_serializer.errors, status=status.HTTP_400_BAD_REQUEST)