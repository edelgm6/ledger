"""
Service functions for paystub upload orchestration.

Handles the full flow: S3 upload -> Gemini parsing -> Paystub/PaystubValue creation.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from api.aws_services import upload_file_to_s3
from api.models import Account, Paystub, PaystubValue, Prefill, S3File
from api.services.gemini_services import parse_paystub_with_gemini

logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    success: bool
    s3file: Optional[S3File] = None
    error: Optional[str] = None


@db_transaction.atomic
def process_paystub_upload(file, prefill: Prefill) -> UploadResult:
    """
    Orchestrates the full paystub upload + parse flow:
    1. Upload file to S3
    2. Create S3File record
    3. Parse PDF with Gemini
    4. Create Paystub + PaystubValue records
    5. Mark analysis complete

    Args:
        file: The uploaded file (Django UploadedFile)
        prefill: The Prefill configuration for this paystub type

    Returns:
        UploadResult with the created S3File on success
    """
    # Read file bytes before uploading (upload may consume the file pointer)
    file.seek(0)
    file_bytes = file.read()
    file.seek(0)

    # 1. Upload to S3
    unique_name = upload_file_to_s3(file=file)
    if isinstance(unique_name, dict):
        return UploadResult(success=False, error=unique_name.get("message", "Upload failed"))

    # 2. Create S3File record
    file_url = (
        f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{unique_name}"
    )
    s3file = S3File.objects.create(
        prefill=prefill,
        url=file_url,
        user_filename=file.name,
        s3_filename=unique_name,
    )

    # 3. Parse with Gemini
    try:
        parsed_data = parse_paystub_with_gemini(file_bytes=file_bytes, prefill=prefill)
    except Exception as e:
        logger.error("Gemini parsing failed: %s", str(e))
        return UploadResult(success=False, s3file=s3file, error=f"Parsing failed: {e}")

    # 4. Create Paystub + PaystubValue records
    create_paystubs_from_data(s3file=s3file, parsed_data=parsed_data, prefill=prefill)

    # 5. Mark analysis complete
    s3file.analysis_complete = timezone.now()
    s3file.save()

    return UploadResult(success=True, s3file=s3file)


def create_paystubs_from_data(
    s3file: S3File,
    parsed_data: Dict[str, Dict[Any, Any]],
    prefill: Prefill,
) -> None:
    """
    Creates Paystub and PaystubValue records from parsed data.

    Extracted from S3File.create_paystubs_from_textract_data() so it can
    be used by both Gemini and Textract paths.

    Args:
        s3file: The S3File record this paystub belongs to
        parsed_data: Dict keyed by page_id with Account -> {value, entry_type, entity} mappings
        prefill: The Prefill for fallback naming
    """
    for page_id, page_data in parsed_data.items():
        company_name = page_data.get("Company", prefill.name)
        end_period = page_data.get("End Period", "")

        paystub = Paystub.objects.create(
            document=s3file,
            page_id=page_id,
            title=f"{company_name} {end_period}".strip(),
        )

        paystub_values = []
        for key, value in page_data.items():
            if not isinstance(key, Account):
                continue
            amount = value["value"]
            if amount != 0:
                paystub_values.append(
                    PaystubValue(
                        paystub=paystub,
                        account=key,
                        amount=amount,
                        journal_entry_item_type=value["entry_type"],
                        entity=value["entity"],
                    )
                )

        PaystubValue.objects.bulk_create(paystub_values)
