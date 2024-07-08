# views.py
import boto3
from django.shortcuts import render
from django.http import JsonResponse
from api.forms import DocumentForm
from django.conf import settings

def upload_document(request):
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            # document = request.FILES['document']
            # response = upload_to_s3(document)
            response = process_document_with_textract('block pay.pdf')
            return JsonResponse(response)
    else:
        form = DocumentForm()
    return render(request, 'upload.html', {'form': form})

def upload_to_s3(file):
    s3_client = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION_NAME
    )
    try:
        s3_client.upload_fileobj(
            file,
            settings.AWS_STORAGE_BUCKET_NAME,
            file.name,
            ExtraArgs={'ContentType': file.content_type}
        )
        file_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{file.name}"
        return {'file_url': file_url, 'message': 'Upload successful'}
    except Exception as e:
        return {'error': str(e), 'message': 'Upload failed'}

def process_document_with_textract(document_name):
    # Boto3 client for Textract
    client = boto3.client(
        'textract',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION_NAME
    )

    # Upload the document to S3 or process it directly
    response = client.start_document_analysis(
        DocumentLocation={
            'S3Object': {
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Name': document_name
            }
        },
        FeatureTypes=[
            'TABLES','FORMS'
        ]
    )
    print(response)
    
    return response
