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

    prompt = f"""Extract the following information from this paystub PDF and return as JSON.

For each page in the document, return an object with these fields:

Metadata:
{metadata_section}

Line Items (extract the dollar amount for each):
{line_items_section}

Return ONLY valid JSON in this exact format (no markdown, no explanation):
{{
  "pages": [
    {{
      "Company": "...",
      "Begin Period": "...",
      "End Period": "...",
      "line_items": {{
        "Account Name": 1234.56,
        ...
      }}
    }}
  ]
}}

Rules:
- Return one object per page in the document
- For line items, return the numeric dollar amount only (no $ sign, no commas)
- If a value is not found on a page, omit it from that page's object
- For metadata fields, return the string value as-is
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
#
# Unlike paystubs (which vary by employer and use DocSearch config), the bill
# field set is fixed, so it lives here in code as a single source of truth:
# (JSON label, UtilityBill field, kind, extraction hint).
BILL_FIELDS = [
    ("Vendor", "vendor", "string", "the utility company / biller name"),
    ("Account Number", "account_number", "string",
     "the utility account number (may be partially masked)"),
    ("Amount Due", "amount", "number",
     "the Payment Amount or Amount Due (the total dollar amount)"),
    ("Service Address", "service_address", "string",
     "the service address (may be partially masked)"),
    ("Bill Date", "bill_date", "date", "the statement or bill date"),
    ("Due Date", "due_date", "date", "the payment due date"),
    ("Payment Date", "payment_date", "date",
     "the date the payment was made or scheduled"),
]


def build_bill_prompt() -> str:
    """Builds the fixed Gemini prompt for extracting utility-bill fields."""
    type_notes = {"number": " (numeric only, no $ sign or commas)", "date": " (a date)", "string": ""}
    field_lines = "\n".join(
        f'- "{label}": {hint}{type_notes[kind]}'
        for label, _field, kind, hint in BILL_FIELDS
    )
    return f"""Extract the following fields from this utility bill email and return as JSON.

Fields:
{field_lines}

Return ONLY valid JSON in this exact format (no markdown, no explanation):
{{
  "Account Number": "...",
  "Amount Due": 1234.56,
  "...": "..."
}}

Rules:
- Return a single JSON object.
- Return amounts as numeric values only (no $ sign, no commas).
- Return values as shown; addresses may be partially masked, so return them exactly as shown.
- If a field is not present, omit it from the object."""


# The bill prompt is invariant (derived only from BILL_FIELDS), so build it once.
BILL_PROMPT = build_bill_prompt()


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


def parse_bill_response(response_text: str) -> Dict[str, Any]:
    """
    Parses Gemini's JSON response for a utility-bill email into a flat dict of
    normalized UtilityBill fields.
    """
    page = _loads_gemini_json(response_text)
    # The prompt asks for a bare object; tolerate a stray {"pages": [...]} wrapper.
    if isinstance(page.get("pages"), list):
        page = page["pages"][0] if page["pages"] else {}

    result: Dict[str, Any] = {}
    for label, field, kind, _hint in BILL_FIELDS:
        if label not in page:
            continue
        value = page[label]
        if kind == "number":
            result[field] = _coerce_bill_amount(value)
        elif kind == "date":
            result[field] = _coerce_bill_date(value)
        else:
            result[field] = str(value).strip()

    return result


def parse_bill_with_gemini(email_text: str) -> Dict[str, Any]:
    """
    High-level function: sends an email body to Gemini with the fixed bill
    prompt and returns normalized UtilityBill fields.
    """
    response_text = call_gemini_text(email_text, BILL_PROMPT)
    return parse_bill_response(response_text)


# --- Recharacterization agent -----------------------------------------------
#
# Translates a plain-language request to recharacterize journal entry items into
# a structured plan (a list of {filter, action} operations) plus a chat reply.
# The model only proposes the plan; recharacterize_services validates and applies
# it deterministically, so the model can never corrupt the books.


def build_recharacterize_system_prompt(
    account_names: List[str],
    entity_names: List[str],
    protected_account_names: List[str],
) -> str:
    """Builds the system instruction for the recharacterization chat."""
    accounts_list = "\n".join(f"- {n}" for n in account_names) or "  (none)"
    entities_list = "\n".join(f"- {n}" for n in entity_names) or "  (none)"
    protected_list = "\n".join(f"- {n}" for n in protected_account_names) or "  (none)"

    return f"""You are a careful bookkeeping assistant for a double-entry \
personal accounting app. You help the user bulk-"recharacterize" past journal \
entry items: re-tagging which entity or account they belong to.

You DO NOT change the ledger yourself. You translate the user's plain-language \
request into a structured plan. A separate deterministic system validates and \
applies it after the user reviews a preview.

Each turn, reply with a SINGLE JSON object:
{{
  "reply": "<short, friendly summary of what you understood and will do, or a \
question if the request is ambiguous>",
  "operations": [ <zero or more operation objects> ]
}}

An operation object:
{{
  "filter": {{
    "description_contains": "<substring of the transaction description, or null>",
    "date_from": "<YYYY-MM-DD or null>",
    "date_to": "<YYYY-MM-DD or null>",
    "account": "<exact account name whose items to target, or null>",
    "entity": "<exact current entity name to match, or null>",
    "entity_is_empty": <true to match only items that currently have NO \
entity (untagged), otherwise false or null>,
    "entry_type": "<'debit', 'credit', or null for either>"
  }},
  "action": {{
    "type": "<'set_entity' | 'clear_entity' | 'change_account'>",
    "entity": "<exact entity name (only for set_entity)>",
    "to_account": "<exact account name (only for change_account)>"
  }}
}}

Rules:
- Use ONLY exact names from the catalogs below. If the user names something not \
in a catalog, do not guess — ask them to clarify in "reply" and return an empty \
operations list.
- A filter must have at least one non-null field. Never produce an operation \
that would match everything.
- When the user targets items with no entity ("empty entity", "untagged", \
"missing entity", "no entity"), set "entity_is_empty" to true (do NOT also set \
"entity"). This counts as a valid filter on its own.
- "change_account" requires "filter.account" (the account to change FROM) and \
"action.to_account" (the account to change TO).
- You may only set/clear an entity or swap an account. You can NEVER change \
amounts or whether an item is a debit or a credit.
- These accounts are system-managed and must NEVER appear in a filter or action; \
if the user asks to touch them, refuse in "reply":
{protected_list}
- A year like "2025" means date_from 2025-01-01 and date_to 2025-12-31.
- Across turns, keep prior operations in mind; when the user refines the request, \
return the full updated operations list.

Accounts:
{accounts_list}

Entities:
{entities_list}
"""


def call_gemini_conversation(system_prompt: str, messages: List[Dict[str, str]]) -> str:
    """Sends a multi-turn conversation to Gemini and returns the raw text.

    ``messages`` is a list of ``{"role": "user"|"assistant", "text": ...}`` dicts
    in chronological order. The response is forced to JSON via response_mime_type.
    """
    from google import genai

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    contents = []
    for message in messages:
        role = "model" if message["role"] == "assistant" else "user"
        contents.append(
            genai.types.Content(
                role=role,
                parts=[genai.types.Part.from_text(text=message["text"])],
            )
        )

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=contents,
        config=genai.types.GenerateContentConfig(
            temperature=0,
            system_instruction=system_prompt,
            response_mime_type="application/json",
        ),
    )

    return response.text
