"""
Service functions for reading utility-bill emails from Gmail.

Auth uses a stored OAuth refresh token (read-only scope) so the poller can run
unattended on a schedule. The mailbox is never modified.
"""
import base64
import logging
import re
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List

from django.conf import settings

logger = logging.getLogger(__name__)

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_TOKEN_URI = "https://oauth2.googleapis.com/token"


def build_gmail_service():
    """Builds an authorized read-only Gmail API client from refresh-token settings."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials(
        token=None,
        refresh_token=settings.GMAIL_REFRESH_TOKEN,
        client_id=settings.GMAIL_CLIENT_ID,
        client_secret=settings.GMAIL_CLIENT_SECRET,
        token_uri=GMAIL_TOKEN_URI,
        scopes=GMAIL_SCOPES,
    )
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def search_messages(
    service, from_address: str, subject: str, newer_than: str = None
) -> List[str]:
    """
    Returns Gmail message IDs matching `from:<from_address> subject:"<subject>"`
    (bounded by a `newer_than:` window). Handles pagination. The window defaults
    to GMAIL_SEARCH_WINDOW_DAYS when not given explicitly.
    """
    if newer_than is None:
        newer_than = f"{settings.GMAIL_SEARCH_WINDOW_DAYS}d"
    query = f'from:{from_address} subject:"{subject}"'
    if newer_than:
        query += f" newer_than:{newer_than}"

    message_ids: List[str] = []
    request = service.users().messages().list(userId="me", q=query)
    while request is not None:
        response = request.execute()
        for message in response.get("messages", []):
            message_ids.append(message["id"])
        request = service.users().messages().list_next(request, response)
    return message_ids


def get_message_text(service, message_id: str) -> Dict[str, Any]:
    """
    Fetches a message and returns
    {from_address, subject, received_at, text} with the plain-text body
    (falling back to stripped HTML).
    """
    message = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    payload = message.get("payload", {})
    headers = {
        header["name"].lower(): header["value"]
        for header in payload.get("headers", [])
    }

    received_at = None
    date_header = headers.get("date")
    if date_header:
        try:
            received_at = parsedate_to_datetime(date_header)
        except (TypeError, ValueError):
            received_at = None

    return {
        "from_address": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "received_at": received_at,
        "text": _extract_plain_text(payload),
    }


def _extract_plain_text(payload: Dict[str, Any]) -> str:
    plain = _find_part_body(payload, "text/plain")
    if plain:
        return plain
    html = _find_part_body(payload, "text/html")
    if html:
        return _strip_html(html)
    return ""


def _find_part_body(part: Dict[str, Any], mime_type: str) -> str:
    if part.get("mimeType") == mime_type:
        data = part.get("body", {}).get("data")
        if data:
            return _decode_b64(data)
    for sub_part in part.get("parts", []) or []:
        found = _find_part_body(sub_part, mime_type)
        if found:
            return found
    return ""


def _decode_b64(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode(
        "utf-8", errors="replace"
    )


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()
