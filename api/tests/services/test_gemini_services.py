import json
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase

from api.models import Account, DocSearch, JournalEntryItem, Prefill
from api.services.gemini_services import (
    build_gemini_prompt,
    call_gemini_api,
    parse_gemini_response,
    parse_paystub_with_gemini,
)
from api.tests.testing_factories import AccountFactory, EntityFactory, PrefillFactory


class BuildGeminiPromptTest(TestCase):
    def setUp(self):
        self.prefill = PrefillFactory(name="Payroll")
        self.account_gross = AccountFactory(
            name="Gross Pay",
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY,
        )
        self.account_fed_tax = AccountFactory(
            name="Federal Tax",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
        )
        self.entity = EntityFactory(name="Employer Inc")

    def test_builds_prompt_with_keyword_searches(self):
        DocSearch.objects.create(
            prefill=self.prefill,
            keyword="Gross Pay",
            account=self.account_gross,
            journal_entry_item_type=JournalEntryItem.JournalEntryType.CREDIT,
            entity=self.entity,
        )
        prompt = build_gemini_prompt(self.prefill)
        self.assertIn("Gross Pay", prompt)
        self.assertIn("key-value pair", prompt)

    def test_builds_prompt_with_table_searches(self):
        DocSearch.objects.create(
            prefill=self.prefill,
            table_name="Tax Deductions",
            row="Federal",
            column="Current",
            account=self.account_fed_tax,
            journal_entry_item_type=JournalEntryItem.JournalEntryType.DEBIT,
            entity=self.entity,
        )
        prompt = build_gemini_prompt(self.prefill)
        self.assertIn("Federal Tax", prompt)
        self.assertIn("Tax Deductions", prompt)

    def test_builds_prompt_with_metadata_selections(self):
        DocSearch.objects.create(
            prefill=self.prefill,
            keyword="Company Name",
            selection="Company",
        )
        DocSearch.objects.create(
            prefill=self.prefill,
            keyword="Pay Period End",
            selection="End Period",
        )
        prompt = build_gemini_prompt(self.prefill)
        self.assertIn('"Company"', prompt)
        self.assertIn('"End Period"', prompt)

    def test_empty_docsearches_returns_valid_prompt(self):
        prompt = build_gemini_prompt(self.prefill)
        self.assertIn("pages", prompt)
        self.assertIn("(none)", prompt)


class ParseGeminiResponseTest(TestCase):
    def setUp(self):
        self.prefill = PrefillFactory(name="Payroll")
        self.entity = EntityFactory(name="Employer Inc")
        self.account_gross = AccountFactory(
            name="Gross Pay",
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY,
        )
        self.account_fed_tax = AccountFactory(
            name="Federal Tax",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
        )
        DocSearch.objects.create(
            prefill=self.prefill,
            keyword="Gross Pay",
            account=self.account_gross,
            journal_entry_item_type=JournalEntryItem.JournalEntryType.CREDIT,
            entity=self.entity,
        )
        DocSearch.objects.create(
            prefill=self.prefill,
            keyword="Federal Tax",
            account=self.account_fed_tax,
            journal_entry_item_type=JournalEntryItem.JournalEntryType.DEBIT,
            entity=self.entity,
        )

    def test_parses_single_page_response(self):
        response_json = json.dumps({
            "pages": [
                {
                    "Company": "Acme Corp",
                    "End Period": "01/15/2026",
                    "line_items": {
                        "Gross Pay": 5000.00,
                        "Federal Tax": 800.50,
                    },
                }
            ]
        })

        result = parse_gemini_response(response_json, self.prefill)

        self.assertIn("0", result)
        page = result["0"]
        self.assertEqual(page["Company"], "Acme Corp")
        self.assertEqual(page["End Period"], "01/15/2026")
        self.assertEqual(page[self.account_gross]["value"], Decimal("5000.00"))
        self.assertEqual(
            page[self.account_gross]["entry_type"],
            JournalEntryItem.JournalEntryType.CREDIT,
        )
        self.assertEqual(page[self.account_gross]["entity"], self.entity)
        self.assertEqual(page[self.account_fed_tax]["value"], Decimal("800.50"))

    def test_parses_multi_page_response(self):
        response_json = json.dumps({
            "pages": [
                {
                    "Company": "Acme Corp",
                    "End Period": "01/15/2026",
                    "line_items": {"Gross Pay": 5000.00},
                },
                {
                    "Company": "Acme Corp",
                    "End Period": "01/31/2026",
                    "line_items": {"Gross Pay": 5200.00},
                },
            ]
        })

        result = parse_gemini_response(response_json, self.prefill)
        self.assertEqual(len(result), 2)
        self.assertEqual(result["0"][self.account_gross]["value"], Decimal("5000.00"))
        self.assertEqual(result["1"][self.account_gross]["value"], Decimal("5200.00"))

    def test_handles_markdown_fenced_response(self):
        response_text = '```json\n{"pages": [{"End Period": "01/15/2026", "line_items": {"Gross Pay": 3000}}]}\n```'

        result = parse_gemini_response(response_text, self.prefill)
        self.assertIn("0", result)
        self.assertEqual(result["0"][self.account_gross]["value"], Decimal("3000.00"))

    def test_skips_unknown_accounts(self):
        response_json = json.dumps({
            "pages": [
                {
                    "End Period": "01/15/2026",
                    "line_items": {
                        "Gross Pay": 5000.00,
                        "Unknown Account": 100.00,
                    },
                }
            ]
        })

        result = parse_gemini_response(response_json, self.prefill)
        page = result["0"]
        # Should have Gross Pay but not Unknown Account
        account_keys = [k for k in page.keys() if isinstance(k, Account)]
        self.assertEqual(len(account_keys), 1)
        self.assertEqual(account_keys[0], self.account_gross)

    def test_missing_metadata_uses_defaults(self):
        response_json = json.dumps({
            "pages": [{"line_items": {"Gross Pay": 1000.00}}]
        })

        result = parse_gemini_response(response_json, self.prefill)
        page = result["0"]
        self.assertNotIn("Company", page)
        self.assertNotIn("End Period", page)


class CallGeminiApiTest(TestCase):
    @patch("google.genai.Client")
    def test_calls_gemini_with_correct_params(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"pages": []}'
        mock_client.models.generate_content.return_value = mock_response

        with self.settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="gemini-2.5-flash"):
            result = call_gemini_api(b"fake-pdf-bytes", "test prompt")

        mock_client_cls.assert_called_once_with(api_key="test-key")
        mock_client.models.generate_content.assert_called_once()
        self.assertEqual(result, '{"pages": []}')


class ParsePaystubWithGeminiTest(TestCase):
    def setUp(self):
        self.prefill = PrefillFactory(name="Payroll")
        self.account = AccountFactory(
            name="Gross Pay",
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY,
        )
        self.entity = EntityFactory(name="Employer")
        DocSearch.objects.create(
            prefill=self.prefill,
            keyword="Gross Pay",
            account=self.account,
            journal_entry_item_type=JournalEntryItem.JournalEntryType.CREDIT,
            entity=self.entity,
        )

    @patch("api.services.gemini_services.call_gemini_api")
    def test_end_to_end_parse(self, mock_call_api):
        mock_call_api.return_value = json.dumps({
            "pages": [
                {
                    "Company": "Test Co",
                    "End Period": "02/01/2026",
                    "line_items": {"Gross Pay": 4500.00},
                }
            ]
        })

        result = parse_paystub_with_gemini(b"pdf-bytes", self.prefill)

        self.assertIn("0", result)
        self.assertEqual(result["0"]["Company"], "Test Co")
        self.assertEqual(result["0"][self.account]["value"], Decimal("4500.00"))
