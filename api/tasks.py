import logging

from celery import shared_task
from django.utils import timezone

from api.aws_services import download_file_from_s3, wait_for_textract_completion
from api.models import S3File
from api.services.gemini_services import parse_paystub_with_gemini
from api.services.paystub_upload_services import create_paystubs_from_data

logger = logging.getLogger(__name__)


@shared_task
def orchestrate_paystub_extraction(s3file_pk):
    s3file = S3File.objects.get(pk=s3file_pk)
    job_id = s3file.create_textract_job()
    wait_for_textract_completion(job_id)
    s3file.create_paystubs_from_textract_data()
    s3file.analysis_complete = timezone.now()
    s3file.save()


@shared_task
def process_gemini_paystub(s3file_pk: int) -> None:
    """
    Celery task: downloads the PDF from S3, calls Gemini, and creates
    Paystub/PaystubValue records. Tracks status at each stage.
    """
    s3file = S3File.objects.select_related("prefill").get(pk=s3file_pk)

    s3file.status = S3File.Status.PROCESSING
    s3file.save(update_fields=["status"])

    try:
        file_bytes = download_file_from_s3(s3file.s3_filename)
        parsed_data = parse_paystub_with_gemini(
            file_bytes=file_bytes, prefill=s3file.prefill
        )
        create_paystubs_from_data(
            s3file=s3file, parsed_data=parsed_data, prefill=s3file.prefill
        )
    except Exception as exc:
        logger.exception("Gemini processing failed for S3File pk=%s", s3file_pk)
        s3file.status = S3File.Status.FAILED
        s3file.error_message = str(exc)
        s3file.save(update_fields=["status", "error_message"])
        raise

    s3file.status = S3File.Status.COMPLETE
    s3file.analysis_complete = timezone.now()
    s3file.save(update_fields=["status", "analysis_complete"])
