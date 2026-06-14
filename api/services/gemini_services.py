"""
Service functions for Gemini-based paystub parsing.

Replaces Textract for extracting structured data from paystub PDFs.
Uses Google Gemini to read PDFs directly and return structured JSON.
"""
import datetime
import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from dateutil import parser as date_parser
from django.conf import settings

from api.models import Account, DocSearch, Prefill

logger = logging.getLogger(__name__)


def build_gemini_prompt(prefill: Prefill, doc_searches: Optional[List] = None) -> str:
    """
    Builds a structured prompt for Gemini from DocSearch records.

    Each DocSearch maps to either a metadata field (selection like "Company",
    "End Period") or a line item (account with dollar amount).
    """
    if doc_searches is None:
        doc_searches = DocSearch.objects.filter(prefill=prefill).select_related(
            "account", "entity"
        )

    metadata_lines = []
    line_item_lines = []

    for ds in doc_searches:
        if ds.selection:
            # Metadata field (Company, Begin Period, End Period)
            hint = _build_hint(ds)
            metadata_lines.append(f'- "{ds.selection}": {hint}')
        elif ds.account:
            # Line item with dollar amount
            hint = _build_hint(ds)
            line_item_lines.append(f'- "{ds.account.name}": {hint}')

    metadata_section = "\n".join(metadata_lines) if metadata_lines else "  (none)"
    line_items_section = "\n".join(line_item_lines) if line_item_lines else "  (none)"

    # Build the example JSON object dynamically from the fields actually
    # requested, so the same builder serves paystubs (metadata + line items)
    # and utility bills (metadata only). Amount-style metadata is shown as a
    # number so the model returns it numerically.
    numeric_labels = {"Amount Due"}
    metadata_selections = [ds.selection for ds in doc_searches if ds.selection]
    has_line_items = any(ds.account and not ds.selection for ds in doc_searches)

    example_lines = []
    for label in metadata_selections:
        placeholder = "1234.56" if label in numeric_labels else '"..."'
        example_lines.append(f'      "{label}": {placeholder}')
    if has_line_items:
        example_lines.append(
            '      "line_items": {\n'
            '        "Account Name": 1234.56,\n'
            "        ...\n"
            "      }"
        )
    if example_lines:
        example_object = "{\n" + ",\n".join(example_lines) + "\n    }"
    else:
        example_object = "{}"

    prompt = f"""Extract the following information from this document and return as JSON.

For each page in the document, return an object with these fields:

Metadata:
{metadata_section}

Line Items (extract the dollar amount for each):
{line_items_section}

Return ONLY valid JSON in this exact format (no markdown, no explanation):
{{
  "pages": [
    {example_object}
  ]
}}

Rules:
- Return one object per page in the document
- For line items and any amount fields, return the numeric dollar amount only (no $ sign, no commas)
- If a value is not found on a page, omit it from that page's object
- For metadata fields, return the value as-is (addresses may be partially masked — return them exactly as shown)
- If multiple values should be summed for the same account, sum them"""

    return prompt


def _build_hint(ds: DocSearch) -> str:
    """Builds a human-readable hint for where to find a value."""
    if ds.keyword:
        return f'look for the key-value pair labeled "{ds.keyword}"'
    parts = []
    if ds.table_name:
        parts.append(f'table "{ds.table_name}"')
    else:
        parts.append("the table")
    if ds.row:
        parts.append(f'row "{ds.row}"')
    if ds.column:
        parts.append(f'column "{ds.column}"')
    return "look in " + ", ".join(parts)


def call_gemini_api(file_bytes: bytes, prompt: str) -> str:
    """
    Sends a PDF file + prompt to Gemini and returns the raw text response.
    """
    from google import genai

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=[
            genai.types.Part.from_bytes(data=file_bytes, mime_type="application/pdf"),
            prompt,
        ],
        config=genai.types.GenerateContentConfig(temperature=0),
    )

    return response.text


def call_gemini_text(text: str, prompt: str) -> str:
    """
    Sends plain text (e.g. an email body) + prompt to Gemini and returns the
    raw text response. Mirrors call_gemini_api but without a PDF Part.
    """
    from google import genai

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=[text, prompt],
        config=genai.types.GenerateContentConfig(temperature=0),
    )

    return response.text


def _loads_gemini_json(response_text: str) -> Dict[str, Any]:
    """Parses a Gemini JSON response, stripping a leading/trailing markdown
    code fence (```json ... ```) if present."""
    text = response_text.strip()
    if text.startswith("```"):
        # Remove the opening fence line (```json or ```) and the closing ```.
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    return json.loads(text)


def parse_gemini_response(
    response_text: str, prefill: Prefill, doc_searches: Optional[List] = None
) -> Dict[str, Dict[Any, Any]]:
    """
    Parses Gemini's JSON response into the data structure expected by
    paystub creation logic.

    Returns:
        Dict keyed by page index (as string) with:
        - "Company": str (optional)
        - "End Period": str
        - Account objects as keys mapping to {"value": Decimal, "entry_type": str, "entity": Entity}
    """
    parsed = _loads_gemini_json(response_text)
    pages = parsed.get("pages", [])

    # Build lookup from account name -> DocSearch for mapping back
    if doc_searches is None:
        doc_searches = DocSearch.objects.filter(prefill=prefill).select_related(
            "account", "entity"
        )
    account_name_to_ds: Dict[str, DocSearch] = {}
    for ds in doc_searches:
        if ds.account:
            account_name_to_ds[ds.account.name] = ds

    result: Dict[str, Dict[Any, Any]] = {}

    for i, page_data in enumerate(pages):
        page_key = str(i)
        page_result: Dict[Any, Any] = {}

        # Extract metadata
        for field in ["Company", "Begin Period", "End Period"]:
            if field in page_data:
                page_result[field] = page_data[field]

        # Extract line items
        line_items = page_data.get("line_items", {})
        for account_name, amount_value in line_items.items():
            ds = account_name_to_ds.get(account_name)
            if not ds:
                logger.warning(
                    "Gemini returned account '%s' not found in DocSearch records",
                    account_name,
                )
                continue

            try:
                decimal_amount = Decimal(str(amount_value)).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                logger.warning(
                    "Could not convert amount '%s' for account '%s'",
                    amount_value,
                    account_name,
                )
                continue

            account = ds.account
            if account in page_result:
                # Sum if already present (same behavior as Textract path)
                page_result[account]["value"] += decimal_amount
            else:
                page_result[account] = {
                    "value": decimal_amount,
                    "entry_type": ds.journal_entry_item_type,
                    "entity": ds.entity,
                }

        result[page_key] = page_result

    return result


def parse_paystub_with_gemini(
    file_bytes: bytes, prefill: Prefill
) -> Dict[str, Dict[Any, Any]]:
    """
    High-level function: sends PDF to Gemini and returns parsed data structure.
    """
    doc_searches = list(
        DocSearch.objects.filter(prefill=prefill).select_related("account", "entity")
    )
    prompt = build_gemini_prompt(prefill, doc_searches=doc_searches)
    response_text = call_gemini_api(file_bytes, prompt)
    return parse_gemini_response(response_text, prefill, doc_searches=doc_searches)


# --- Utility-bill email extraction -----------------------------------------

# Maps the Gemini metadata labels (DocSearch.selection) to UtilityBill fields.
BILL_LABEL_TO_FIELD = {
    "Vendor": "vendor",
    "Account Number": "account_number",
    "Amount Due": "amount",
    "Service Address": "service_address",
    "Bill Date": "bill_date",
    "Due Date": "due_date",
    "Payment Date": "payment_date",
}


def _coerce_bill_amount(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        logger.warning("Could not convert bill amount '%s'", value)
        return None


def _coerce_bill_date(value: Any) -> Optional[datetime.date]:
    if not value:
        return None
    try:
        return date_parser.parse(str(value)).date()
    except (ValueError, OverflowError):
        logger.warning("Could not parse bill date '%s'", value)
        return None


def parse_bill_response(response_text: str, prefill: Prefill) -> Dict[str, Any]:
    """
    Parses Gemini's JSON response for a utility-bill email into a flat dict of
    normalized UtilityBill fields. A bill is treated as a single-page document,
    so only pages[0] is read.
    """
    parsed = _loads_gemini_json(response_text)
    pages = parsed.get("pages", [])
    page = pages[0] if pages else {}

    result: Dict[str, Any] = {}
    for label, field in BILL_LABEL_TO_FIELD.items():
        if label not in page:
            continue
        value = page[label]
        if field == "amount":
            result[field] = _coerce_bill_amount(value)
        elif field in ("bill_date", "due_date", "payment_date"):
            result[field] = _coerce_bill_date(value)
        else:
            result[field] = str(value).strip()

    return result


def parse_bill_with_gemini(email_text: str, prefill: Prefill) -> Dict[str, Any]:
    """
    High-level function: sends an email body to Gemini using the bill prefill's
    DocSearch config and returns normalized UtilityBill fields.
    """
    doc_searches = list(
        DocSearch.objects.filter(prefill=prefill).select_related("account", "entity")
    )
    prompt = build_gemini_prompt(prefill, doc_searches=doc_searches)
    response_text = call_gemini_text(email_text, prompt)
    return parse_bill_response(response_text, prefill)
