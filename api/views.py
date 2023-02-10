from django.shortcuts import render
from rest_framework.parsers import FileUploadParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from .serializers import TransactionCsvSerializer, TransactionOutputSerializer, JournalEntryInputSerializer, JournalEntryOutputSerializer

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