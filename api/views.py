from django.shortcuts import render
from django.views import View
from django.http import HttpResponseRedirect
from rest_framework.parsers import FileUploadParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from api.serializers import TransactionOutputSerializer, JournalEntryInputSerializer, JournalEntryOutputSerializer
from api.forms import TransactionsUploadForm
from api.CsvHandler import CsvHandler


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


class TransactionsUploadViewChase(APIView):
    parser_class = (FileUploadParser,)

    def post(self, request, *args, **kwargs):
        print(request.data)
        transactions_serializer = ChaseCsvSerializer(data=request.data, many=True)
        if transactions_serializer.is_valid():
            print(valid)
            transactions = transactions_serializer.save()
            transactions_output_serializer = TransactionOutputSerializer(transactions,many=True)
            return Response(transactions_output_serializer.data, status=status.HTTP_201_CREATED)
        else:
            print(transactions_serializer.errors)
            return Response(transactions_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TransactionsUploadView(APIView):
    parser_class = (FileUploadParser,)

    def post(self, request, *args, **kwargs):
        print(request.data)
        file_serializer = TransactionCsvSerializer(data=request.data)
        if file_serializer.is_valid():
            files = file_serializer.save()
            transactions_output_serializer = TransactionOutputSerializer(files,many=True)
            return Response(transactions_output_serializer.data, status=status.HTTP_201_CREATED)
        else:
            print(file_serializer.errors)
            return Response(file_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class JournalEntryView(APIView):

    def post(self, request, *args, **kwargs):

        print(request.data)

        journal_entry_input_serializer = JournalEntryInputSerializer(data=request.data)

        if journal_entry_input_serializer.is_valid():
            journal_entry = journal_entry_input_serializer.save()
            journal_entry_output_serializer = JournalEntryOutputSerializer(journal_entry)
            return Response(journal_entry_output_serializer.data, status=status.HTTP_201_CREATED)
        else:
            print(journal_entry_input_serializer.errors)
            return Response(journal_entry_input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)