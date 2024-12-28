import re
import uuid
from decimal import Decimal
from time import sleep

import boto3
from botocore.exceptions import ClientError
from django.conf import settings


def get_boto3_client(service="textract"):
    client = boto3.client(
        service,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION_NAME,
        verify=settings.AWS_VERIFY,
    )
    return client


def upload_file_to_s3(file):
    s3_client = get_boto3_client(service="s3")
    unique_name = generate_unique_filename(file)
    try:
        s3_client.upload_fileobj(
            file,
            settings.AWS_STORAGE_BUCKET_NAME,
            unique_name,
            ExtraArgs={"ContentType": file.content_type},
        )
        return unique_name
    except Exception as e:
        print(str(e))
        return {"error": str(e), "message": "Upload failed"}


def generate_unique_filename(file):
    ext = file.name.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{ext}"
    return unique_filename


def create_textract_job(filename):
    # Boto3 client for Textract
    client = get_boto3_client()

    # Process file
    response = client.start_document_analysis(
        DocumentLocation={
            "S3Object": {"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Name": filename}
        },
        FeatureTypes=["FORMS", "TABLES"],
    )
    job_id = response.get("JobId")
    return job_id


def wait_for_textract_completion(job_id):
    POLLING_INTERVAL = 10  # Time in seconds between polls
    MAX_ATTEMPTS = 30  # Maximum number of polling attempts

    client = get_boto3_client()

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = client.get_document_analysis(JobId=job_id)
            job_status = response.get("JobStatus")

            if job_status == "SUCCEEDED":
                # Job is complete; exit the loop
                return
            elif job_status == "FAILED":
                raise RuntimeError(
                    f"Textract job failed: {response.get('StatusMessage')}"
                )
            elif job_status == "IN_PROGRESS":
                # Wait and poll again
                sleep(POLLING_INTERVAL)
            else:
                raise RuntimeError(f"Unexpected job status: {job_status}")
        except ClientError as e:
            raise RuntimeError(f"An error occurred while polling Textract: {str(e)}")

    # If the maximum attempts are reached, raise an exception
    raise TimeoutError(
        f"Textract job {job_id} did not complete within the allowed time."
    )


# Get all responses, paginated
def get_textract_results(job_id):

    client = get_boto3_client()

    responses = []
    next_token = None
    while True:
        if next_token:
            response = client.get_document_analysis(JobId=job_id, NextToken=next_token)
        else:
            response = client.get_document_analysis(JobId=job_id)

        responses.append(response)
        next_token = response.get("NextToken")
        if not next_token:
            break

    combined_response = combine_responses(responses)
    return combined_response


def combine_responses(responses):
    combined_response = {"DocumentMetadata": {"Pages": ""}, "Blocks": []}

    for response in responses:
        try:
            combined_response["DocumentMetadata"]["Pages"] = response[
                "DocumentMetadata"
            ]["Pages"]
        except KeyError:
            pass
        combined_response["Blocks"].extend(response["Blocks"])

    return combined_response


def convert_table_to_cleaned_dataframe(table):
    no_titles_table = table.strip_headers(
        column_headers=False, in_table_title=True, section_titles=True
    )

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


def clean_string(input_string):
    if input_string is None:
        return None
    # Remove commas
    cleaned_string = input_string.replace(",", "")

    # Remove starting/trailing whitespace and ensure only one space between words
    cleaned_string = " ".join(cleaned_string.split())

    return cleaned_string


def clean_and_convert_string_to_decimal(input_string):
    if not input_string:
        return Decimal("0.00")
    cleaned_string = clean_string(input_string)
    cleaned_string = cleaned_string.replace(",", "").replace("$", "")
    cleaned_string = re.sub(r"[^\d.]", "", cleaned_string)
    return Decimal(cleaned_string).quantize(Decimal("0.00"))
