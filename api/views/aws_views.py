import boto3
import json
from django.shortcuts import render
from django.http import JsonResponse
from api.forms import DocumentForm
from django.conf import settings
from textractor.entities.document import Document

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
            extract_relevant_data(output_path)
            return JsonResponse()
    else:
        form = DocumentForm()
    return render(request, 'upload.html', {'form': form})

def clean_string(input_string):
    # Remove commas
    cleaned_string = input_string.replace(',', '')
    
    # Remove starting/trailing whitespace and ensure only one space between words
    cleaned_string = ' '.join(cleaned_string.split())
    
    return cleaned_string

def extract_relevant_data(document_location):
    
    # Load the Textract response from the JSON file using textractor
    document = Document.open(document_location)
    print('opened doc')

    # Step 1: Build pages data structure
    page_ids = []
    data = {}
    for page in document.pages:
        page_id = page.id
        page_ids.append(page_id)
        data[page_id] = {}

    # Step 2: Name each page and create a data structure
    # Extract key-value pairs
    key_value_pairs = document.key_values

    # Print the key-value pairs and create data object
    for kv in key_value_pairs:
        key = clean_string(kv.key.text)
        if key == 'Company':
            company = kv.value.text
            data[kv.page_id]['Company'] = company
        if key == 'Pay Period End':
            end_period = kv.value.text
            data[kv.page_id]['End Period'] = end_period
        if key == 'Pay Period Begin':
            begin_period = kv.value.text
            data[kv.page_id]['Begin Period'] = begin_period

    # Step 3: Grab table data from unnamed tables
    unnamed_tables = [table for table in document.tables if table.title is None]
    for table in unnamed_tables:
        pandas_table = convert_table_to_cleaned_dataframe(table)
        try:
            gross_pay_current = pandas_table.loc['Current', 'Gross Pay']
            data[page_id]['gross'] = gross_pay_current.strip()
        except KeyError:
            continue

    # Step 4: Grab data from named tables
    # Step 4a: Grab taxes
    table_data_collection = [
        {
            'table_title': 'Employee Taxes',
            'row': 'OASDI',
            'column': 'Amount'
        },
        {
            'table_title': 'Employee Taxes',
            'row': 'Medicare',
            'column': 'Amount'
        },
        {
            'table_title': 'Employee Taxes',
            'row': 'Federal Withholding',
            'column': 'Amount'
        },
        {
            'table_title': 'Employee Taxes',
            'row': 'State Tax GA', #TODO: This should actually have a dash — for some reason textract removes it
            'column': 'Amount'
        },
        {
            'table_title': 'Deductions',
            'row': '401K',
            'column': 'Amount'
        },
        {
            'table_title': 'Deductions',
            'row': 'Dental Pre Tax',
            'column': 'Amount'
        },
        {
            'table_title': 'Deductions',
            'row': 'HSA',
            'column': 'Amount'
        },
        {
            'table_title': 'Deductions',
            'row': 'Medical Pre Tax',
            'column': 'Amount'
        },
        {
            'table_title': 'Deductions',
            'row': 'Vision Pre Tax',
            'column': 'Amount'
        },
        {
            'table_title': 'Employee Post Tax Deductions',
            'row': 'Employee Stock Purchase Plan',
            'column': 'Amount'
        },
        {
            'table_title': 'Employee Post Tax Deductions',
            'row': 'Voluntary Accident',
            'column': 'Amount'
        },
        {
            'table_title': 'Employee Post Tax Deductions',
            'row': 'Voluntary Critical Illness',
            'column': 'Amount'
        },
        {
            'table_title': 'Employee Post Tax Deductions',
            'row': 'Voluntary Hospital',
            'column': 'Amount'
        },
        {
            'table_title': 'Payment Information',
            'row': 'Ally Bank',
            'column': 'Amount'
        },
        {
            'table_title': 'Payment Information',
            'row': 'FIRST REPUBLIC BANK',
            'column': 'Amount'
        }
    ]
    
    named_tables = [table for table in document.tables if table.title is not None]
    for table in named_tables:
        collection_dicts = [dict for dict in table_data_collection if dict['table_title'] == table.title.text]
        # Clean the table per the pandas notes above
        pandas_table = convert_table_to_cleaned_dataframe(table)
        for dict in collection_dicts:
            value = pandas_table.loc[dict['row'], dict['column']]
            data[page_id][dict['row']] = value.strip()

    print(data)

def convert_table_to_cleaned_dataframe(table):
    no_titles_table = table.strip_headers(column_headers=False, in_table_title=True, section_titles=True)
    
    pandas_table = no_titles_table.to_pandas()

    # Set the first row as the header
    pandas_table.columns = pandas_table.iloc[0]
    pandas_table = pandas_table[1:]

    # Set the first column as the index
    pandas_table.set_index(pandas_table.columns[0], inplace=True)

    # Strip whitespace from column names and index
    pandas_table.columns = pandas_table.columns.str.strip()
    pandas_table.index = pandas_table.index.str.strip()

    return pandas_table

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