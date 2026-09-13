"""
Service functions for paystub upload orchestration.

Handles the full flow: S3 upload -> dispatch async Gemini task -> Paystub/PaystubValue creation.
"""
import logging
from dataclasses import dataclass
from typing import Dict, Optional

from django.conf import settings

from api.aws_services import upload_file_to_s3
from api.models import Paystub, PaystubValue, Prefill, S3File
from api.services.gemini_services import ExtractedPage

logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    success: bool
    s3file: Optional[S3File] = None
    error: Optional[str] = None


def _dispatch_gemini_processing(s3file_pk: int) -> None:
    """Dispatches the async Gemini paystub task.

    The import is local because api.tasks imports from this module.
    """
    from api.tasks import process_gemini_paystub

    process_gemini_paystub.delay(s3file_pk)


def process_paystub_upload(file, prefill: Prefill) -> UploadResult:
    """
    Orchestrates the paystub upload flow:
    1. Upload file to S3
    2. Create S3File record (status defaults to PENDING)
    3. Dispatch Celery task to call Gemini and create Paystub/PaystubValue records

    Args:
        file: The uploaded file (Django UploadedFile)
        prefill: The Prefill configuration for this paystub type

    Returns:
        UploadResult with the created S3File on success
    """
    # 1. Upload to S3 (network call)
    unique_name = upload_file_to_s3(file=file)
    if isinstance(unique_name, dict):
        return UploadResult(success=False, error=unique_name.get("message", "Upload failed"))

    # 2. Create S3File immediately so the poller can show a pending state
    file_url = (
        f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{unique_name}"
    )
    s3file = S3File.objects.create(
        prefill=prefill,
        url=file_url,
        user_filename=file.name,
        s3_filename=unique_name,
    )

    # 3. Dispatch Celery task — Gemini call and DB writes happen on the worker
    _dispatch_gemini_processing(s3file.pk)

    return UploadResult(success=True, s3file=s3file)


def retry_paystub_processing(s3file_id: int) -> UploadResult:
    """
    Resets a failed S3File to PENDING and re-dispatches the Gemini task.

    Used by the Retry button on the paystubs poller when Gemini returns a
    transient error (e.g. 503 UNAVAILABLE).
    """
    s3file = S3File.objects.get(pk=s3file_id)
    s3file.status = S3File.Status.PENDING
    s3file.error_message = ""
    s3file.save(update_fields=["status", "error_message"])

    _dispatch_gemini_processing(s3file.pk)

    return UploadResult(success=True, s3file=s3file)


def create_paystubs_from_data(
    s3file: S3File,
    parsed_data: Dict[str, ExtractedPage],
    prefill: Prefill,
) -> None:
    """
    Creates Paystub and PaystubValue records from parsed pages.

    Args:
        s3file: The S3File record this paystub belongs to
        parsed_data: Dict keyed by page_id -> ExtractedPage
        prefill: The Prefill for fallback naming
    """
    for page_id, page in parsed_data.items():
        paystub = Paystub.objects.create(
            document=s3file,
            page_id=page_id,
            title=page.title_for(prefill.name),
        )

        # Metadata and line items are separate fields now, so telling them
        # apart no longer needs an isinstance(key, Account) filter.
        PaystubValue.objects.bulk_create(
            [
                PaystubValue(
                    paystub=paystub,
                    account=value.account,
                    amount=value.amount,
                    journal_entry_item_type=value.entry_type,
                    entity=value.entity,
                )
                for value in page.values
                if value.amount != 0
            ]
        )
