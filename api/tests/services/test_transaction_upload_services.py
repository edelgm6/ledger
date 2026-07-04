from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from api.forms import UploadTransactionsForm
from api.services.transaction_upload_services import import_transactions_from_csv
from api.tests.testing_factories import AccountFactory


class ImportTransactionsFromCsvTest(TestCase):
    def setUp(self):
        # AccountFactory attaches a csv_profile, so the account passes the form's
        # queryset filter (Account.objects.filter(csv_profile__isnull=False)).
        self.account = AccountFactory()

    def _valid_form(self):
        upload = SimpleUploadedFile(
            "transactions.csv", b"date,amount\n", content_type="text/csv"
        )
        form = UploadTransactionsForm(
            {"account": self.account.pk}, {"transaction_csv": upload}
        )
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def test_successful_import_returns_count_and_account(self):
        # form.save() returns the created transactions; the service counts them
        # and tags them (tagging is exercised in test_tagging_services).
        form = self._valid_form()
        created = [object(), object(), object(), object(), object()]
        with patch.object(form, "save", return_value=created), patch(
            "api.services.transaction_upload_services.tag_transactions"
        ) as mock_tag:
            result = import_transactions_from_csv(form)

        self.assertTrue(result.success)
        self.assertEqual(result.count, 5)
        self.assertEqual(result.account, self.account)
        self.assertIsNone(result.error)
        mock_tag.assert_called_once_with(created)

    def test_zero_rows_is_still_success(self):
        form = self._valid_form()
        with patch.object(form, "save", return_value=[]), patch(
            "api.services.transaction_upload_services.tag_transactions"
        ):
            result = import_transactions_from_csv(form)

        self.assertTrue(result.success)
        self.assertEqual(result.count, 0)
        self.assertEqual(result.account, self.account)

    def test_exception_during_import_returns_error(self):
        form = self._valid_form()
        with patch.object(form, "save", side_effect=Exception("bad columns")):
            result = import_transactions_from_csv(form)

        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
