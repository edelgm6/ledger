import logging
import uuid

import boto3
from django.conf import settings

logger = logging.getLogger(__name__)


def get_boto3_client(service="s3"):
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
        logger.error("S3 upload failed: %s", str(e))
        return {"error": str(e), "message": "Upload failed"}


def generate_unique_filename(file):
    ext = file.name.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{ext}"
    return unique_filename


def download_file_from_s3(s3_filename: str) -> bytes:
    s3_client = get_boto3_client(service="s3")
    response = s3_client.get_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=s3_filename,
    )
    return response["Body"].read()
