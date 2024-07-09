import boto3
import json
from django.shortcuts import render
from django.http import JsonResponse
from api.forms import DocumentForm
from django.conf import settings
from textractor.entities.document import Document
from textractor.data.text_linearization_config import TextLinearizationConfig

def upload_document(request):
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            # document = request.FILES['document']
            # response = upload_to_s3(document)
            # response = process_document_with_textract('block pay.pdf')
            # return JsonResponse(response)
            responses = get_textract_results('7832f55c93c6b71f5e2372e32ef7814798e9b1a2ffd91f8c87f860d655c140df')
            print('got all responses')
            combined_response = combine_responses(responses)
            print('combined responses')

            # Save combined response to a file
            output_path = "/Users/garrett.edel@opendoor.com/Desktop/ledger/ledger/api/textract_response.json"
            with open(output_path, 'w') as f:
                json.dump(combined_response, f)
            print('saved output')

            # Load the Textract response from the JSON file using textractor
            document = Document.open(output_path)
            print('opened doc')

            # # Extract key-value pairs
            # key_value_pairs = document.key_values

            # # Print the key-value pairs
            # for kv in key_value_pairs:
            #     print(f"Key: {kv.key}, Value: {kv.value}")

            tables = document.tables
            for table in tables:
                # print(table.page)
                try:
                    title = table.title.text
                except:
                    title = None

                if title == 'Employee Taxes':
                    csv = table.to_csv(config=TextLinearizationConfig(
                        max_number_of_consecutive_spaces=1,
                        add_prefixes_and_suffixes_in_text=False
                    ))
                    # cells = table.get_text_and_words()
                    print(csv)
                    # for row in cells['Description']:
                        # print(row.text)
                
                # print(table.get_text_and_words())

            return JsonResponse()
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
            'FORMS','TABLES'
        ]
    )
    print(response)
    
    return response

# Get all responses, paginated
def get_textract_results(job_id):
    client = boto3.client(
        'textract',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION_NAME
    )

    responses = []
    next_token = None
    while True:
        if next_token:
            response = client.get_document_analysis(JobId=job_id, NextToken=next_token)
        else:
            response = client.get_document_analysis(JobId=job_id)
        
        responses.append(response)
        next_token = response.get('NextToken')
        if not next_token:
            break
    return responses

# Combine responses
# TODO: Fix the pages logic here
def combine_responses(responses):
    combined_response = {
        "DocumentMetadata": {
            "Pages": 1
        },
        "Blocks": []
    }

    for response in responses:
        # print(response)
        combined_response["DocumentMetadata"]["Pages"] #+= response["DocumentMetadata"]["Pages"]
        combined_response["Blocks"].extend(response["Blocks"])

    return combined_response