from django.shortcuts import render
from rest_framework.parsers import FileUploadParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from .serializers import TransactionsCsvSerializer, TransactionsOutputSerializer

class TransactionsUploadView(APIView):
    parser_class = (FileUploadParser,)

    def post(self, request, *args, **kwargs):
        print(request.data)
        file_serializer = TransactionsCsvSerializer(data=request.data)
        if file_serializer.is_valid():
            files = file_serializer.save()
            transactions_output_serializer = TransactionsOutputSerializer(files,many=True)
            return Response(transactions_output_serializer.data, status=status.HTTP_201_CREATED)
        else:
            print(file_serializer.errors)
            return Response(file_serializer.errors, status=status.HTTP_400_BAD_REQUEST)