from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase

from api.models import (
    Account,
    DocSearch,
    JournalEntryItem,
    Paystub,
    PaystubValue,
    S3File,
)
from api.services.paystub_upload_services import (
    create_paystubs_from_data,
    process_paystub_upload,
)
from api.tests.testing_factories import AccountFactory, EntityFactory, PrefillFactory


class CreatePaystubsFromDataTest(TestCase):
    def setUp(self):
        self.prefill = PrefillFactory(name="Payroll")
        self.entity = EntityFactory(name="Employer")
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
        self.s3file = S3File.objects.create(
            prefill=self.prefill,
            url="https://bucket.s3.amazonaws.com/test.pdf",
            user_filename="test.pdf",
            s3_filename="uuid-test.pdf",
        )

    def test_creates_paystub_and_values(self):
        parsed_data = {
            "0": {
                "Company": "Acme Corp",
                "End Period": "01/15/2026",
                self.account_gross: {
                    "value": Decimal("5000.00"),
                    "entry_type": JournalEntryItem.JournalEntryType.CREDIT,
                    "entity": self.entity,
                },
                self.account_fed_tax: {
                    "value": Decimal("800.00"),
                    "entry_type": JournalEntryItem.JournalEntryType.DEBIT,
                    "entity": self.entity,
                },
            }
        }

        create_paystubs_from_data(
            s3file=self.s3file, parsed_data=parsed_data, prefill=self.prefill
        )

        paystubs = Paystub.objects.filter(document=self.s3file)
        self.assertEqual(paystubs.count(), 1)

        paystub = paystubs.first()
        self.assertEqual(paystub.title, "Acme Corp 01/15/2026")
        self.assertEqual(paystub.page_id, "0")

        values = PaystubValue.objects.filter(paystub=paystub)
        self.assertEqual(values.count(), 2)

        gross_val = values.get(account=self.account_gross)
        self.assertEqual(gross_val.amount, Decimal("5000.00"))
        self.assertEqual(
            gross_val.journal_entry_item_type,
            JournalEntryItem.JournalEntryType.CREDIT,
        )
        self.assertEqual(gross_val.entity, self.entity)

    def test_skips_zero_amounts(self):
        parsed_data = {
            "0": {
                "End Period": "01/15/2026",
                self.account_gross: {
                    "value": Decimal("0.00"),
                    "entry_type": JournalEntryItem.JournalEntryType.CREDIT,
                    "entity": self.entity,
                },
            }
        }

        create_paystubs_from_data(
            s3file=self.s3file, parsed_data=parsed_data, prefill=self.prefill
        )

        values = PaystubValue.objects.filter(paystub__document=self.s3file)
        self.assertEqual(values.count(), 0)

    def test_uses_prefill_name_when_company_missing(self):
        parsed_data = {
            "0": {
                "End Period": "01/15/2026",
                self.account_gross: {
                    "value": Decimal("1000.00"),
                    "entry_type": JournalEntryItem.JournalEntryType.CREDIT,
                    "entity": self.entity,
                },
            }
        }

        create_paystubs_from_data(
            s3file=self.s3file, parsed_data=parsed_data, prefill=self.prefill
        )

        paystub = Paystub.objects.get(document=self.s3file)
        self.assertTrue(paystub.title.startswith(self.prefill.name))

    def test_creates_multiple_paystubs_for_multi_page(self):
        parsed_data = {
            "0": {
                "Company": "Acme",
                "End Period": "01/15/2026",
                self.account_gross: {
                    "value": Decimal("5000.00"),
                    "entry_type": JournalEntryItem.JournalEntryType.CREDIT,
                    "entity": self.entity,
                },
            },
            "1": {
                "Company": "Acme",
                "End Period": "01/31/2026",
                self.account_gross: {
                    "value": Decimal("5200.00"),
                    "entry_type": JournalEntryItem.JournalEntryType.CREDIT,
                    "entity": self.entity,
                },
            },
        }

        create_paystubs_from_data(
            s3file=self.s3file, parsed_data=parsed_data, prefill=self.prefill
        )

        paystubs = Paystub.objects.filter(document=self.s3file)
        self.assertEqual(paystubs.count(), 2)


class ProcessPaystubUploadTest(TestCase):
    def setUp(self):
        self.prefill = PrefillFactory(name="Payroll")
        self.entity = EntityFactory(name="Employer")
        self.account = AccountFactory(
            name="Gross Pay",
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY,
        )
        DocSearch.objects.create(
            prefill=self.prefill,
            keyword="Gross Pay",
            account=self.account,
            journal_entry_item_type=JournalEntryItem.JournalEntryType.CREDIT,
            entity=self.entity,
        )

    @patch("api.services.paystub_upload_services.parse_paystub_with_gemini")
    @patch("api.services.paystub_upload_services.upload_file_to_s3")
    def test_successful_upload(self, mock_upload, mock_parse):
        mock_upload.return_value = "uuid-test.pdf"
        mock_parse.return_value = {
            "0": {
                "Company": "Test Co",
                "End Period": "01/15/2026",
                self.account: {
                    "value": Decimal("4500.00"),
                    "entry_type": JournalEntryItem.JournalEntryType.CREDIT,
                    "entity": self.entity,
                },
            }
        }

        mock_file = MagicMock()
        mock_file.name = "paystub.pdf"
        mock_file.read.return_value = b"fake-pdf"

        with self.settings(AWS_STORAGE_BUCKET_NAME="test-bucket"):
            result = process_paystub_upload(file=mock_file, prefill=self.prefill)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.s3file)
        self.assertIsNotNone(result.s3file.analysis_complete)

        paystubs = Paystub.objects.filter(document=result.s3file)
        self.assertEqual(paystubs.count(), 1)
        self.assertEqual(paystubs.first().title, "Test Co 01/15/2026")

    @patch("api.services.paystub_upload_services.upload_file_to_s3")
    def test_s3_upload_failure(self, mock_upload):
        mock_upload.return_value = {"error": "Access Denied", "message": "Upload failed"}

        mock_file = MagicMock()
        mock_file.name = "paystub.pdf"
        mock_file.read.return_value = b"fake-pdf"

        result = process_paystub_upload(file=mock_file, prefill=self.prefill)

        self.assertFalse(result.success)
        self.assertEqual(result.error, "Upload failed")

    @patch("api.services.paystub_upload_services.parse_paystub_with_gemini")
    @patch("api.services.paystub_upload_services.upload_file_to_s3")
    def test_gemini_parse_failure(self, mock_upload, mock_parse):
        mock_upload.return_value = "uuid-test.pdf"
        mock_parse.side_effect = Exception("API error")

        mock_file = MagicMock()
        mock_file.name = "paystub.pdf"
        mock_file.read.return_value = b"fake-pdf"

        with self.settings(AWS_STORAGE_BUCKET_NAME="test-bucket"):
            result = process_paystub_upload(file=mock_file, prefill=self.prefill)

        self.assertFalse(result.success)
        self.assertIn("Parsing failed", result.error)
        # S3File should still be created
        self.assertIsNotNone(result.s3file)
