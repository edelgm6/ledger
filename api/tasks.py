from celery import shared_task

from api.aws_services import wait_for_textract_completion
from api.models import S3File


@shared_task
def orchestrate_paystub_extraction(s3file_pk):
    s3file = S3File.objects.get(pk=s3file_pk)
    job_id = s3file.create_textract_job()
    wait_for_textract_completion(job_id)
    s3file.create_paystubs_from_textract_data()


@shared_task
def add(x, y):
    return x + y