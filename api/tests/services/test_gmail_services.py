import base64
from unittest.mock import MagicMock

from django.test import TestCase

from api.services.gmail_services import (
    _strip_html,
    get_message_text,
    search_messages,
)


def _b64(text):
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8")


class SearchMessagesTest(TestCase):
    def test_builds_query_and_collects_ids(self):
        service = MagicMock()
        messages = service.users.return_value.messages.return_value
        request = MagicMock()
        messages.list.return_value = request
        request.execute.return_value = {"messages": [{"id": "a"}, {"id": "b"}]}
        messages.list_next.return_value = None

        ids = search_messages(service, "billing@x.com", "Your bill")

        self.assertEqual(ids, ["a", "b"])
        _, kwargs = messages.list.call_args
        self.assertIn("from:billing@x.com", kwargs["q"])
        self.assertIn('subject:"Your bill"', kwargs["q"])
        self.assertIn("newer_than:60d", kwargs["q"])

    def test_paginates(self):
        service = MagicMock()
        messages = service.users.return_value.messages.return_value
        first, second = MagicMock(), MagicMock()
        messages.list.return_value = first
        first.execute.return_value = {"messages": [{"id": "a"}]}
        second.execute.return_value = {"messages": [{"id": "b"}]}
        messages.list_next.side_effect = [second, None]

        self.assertEqual(search_messages(service, "f", "s"), ["a", "b"])


class GetMessageTextTest(TestCase):
    def test_decodes_plain_text_and_headers(self):
        service = MagicMock()
        get_request = service.users.return_value.messages.return_value.get.return_value
        get_request.execute.return_value = {
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [
                    {"name": "From", "value": "billing@x.com"},
                    {"name": "Subject", "value": "Your bill"},
                    {"name": "Date", "value": "Wed, 10 Jun 2026 12:00:00 -0400"},
                ],
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": _b64("Amount due $88.42")},
                    },
                ],
            }
        }

        result = get_message_text(service, "id1")

        self.assertEqual(result["from_address"], "billing@x.com")
        self.assertEqual(result["subject"], "Your bill")
        self.assertIn("88.42", result["text"])
        self.assertIsNotNone(result["received_at"])

    def test_falls_back_to_stripped_html(self):
        service = MagicMock()
        get_request = service.users.return_value.messages.return_value.get.return_value
        get_request.execute.return_value = {
            "payload": {
                "mimeType": "text/html",
                "headers": [],
                "body": {"data": _b64("<p>Amount <b>$88.42</b></p>")},
            }
        }

        result = get_message_text(service, "id1")
        self.assertIn("88.42", result["text"])
        self.assertNotIn("<p>", result["text"])


class StripHtmlTest(TestCase):
    def test_strips_tags_and_collapses_whitespace(self):
        self.assertEqual(_strip_html("<p>Hello   <b>world</b></p>"), "Hello world")
