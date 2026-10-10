"""Two small user-facing bugs from the audit's lower-value accepted list.

S13-b: a BOM-prefixed CSV export (what Excel and most Windows tools produce)
was decoded as strict utf-8, which does not raise but leaves U+FEFF glued to
the first column header -- so the profile's date/description/amount lookups
missed and the import failed on a file that looks fine to the user.

S18: Amortization.periods is nullable on the model, so the form field was not
required, so a blank submit reached `periods < 1` and raised TypeError rather
than a validation error.
"""

import datetime
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from api.forms import AmortizationForm, UploadTransactionsForm
from api.models import (
    Account,
    Amortization,
    JournalEntry,
    JournalEntryItem,
    Transaction,
)
from api.tests.testing_factories import (
    AccountFactory,
    CSVProfileFactory,
    TransactionFactory,
)

CSV_BODY = (
    "Date,Description,Category,Inflow,Outflow\n"
    "2026-03-01,Coffee,Food,,4.50\n"
    "2026-03-02,Paycheck,Income,1000.00,\n"
)


class CSVBomHandlingTest(TestCase):
    def setUp(self):
        self.profile = CSVProfileFactory(
            name="Bank",
            date="Date",
            description="Description",
            category="Category",
            clear_prepended_until_value="",
            inflow="Inflow",
            outflow="Outflow",
            date_format="%Y-%m-%d",
        )
        self.account = AccountFactory(
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            csv_profile=self.profile,
        )

    def _upload(self, raw: bytes):
        form = UploadTransactionsForm(
            data={"account": str(self.account.id)},
            files={
                "transaction_csv": SimpleUploadedFile(
                    "export.csv", raw, content_type="text/csv"
                )
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()

    def test_plain_utf8_export_imports(self):
        created = self._upload(CSV_BODY.encode("utf-8"))
        self.assertEqual(len(created), 2)

    def test_bom_prefixed_export_imports(self):
        """The regression: Excel writes a BOM. utf-8 decodes it to U+FEFF
        rather than raising, so the first header became '﻿Date' and the
        profile's date column lookup missed."""
        created = self._upload(CSV_BODY.encode("utf-8-sig"))
        self.assertEqual(
            len(created), 2, "a BOM-prefixed export must import like any other"
        )
        self.assertEqual(
            {t.description for t in created}, {"Coffee", "Paycheck"}
        )

    def test_bom_does_not_leak_into_the_first_column_value(self):
        created = self._upload(CSV_BODY.encode("utf-8-sig"))
        for transaction in created:
            self.assertIsInstance(transaction.date, datetime.date)


class AmortizationPeriodsValidationTest(TestCase):
    def setUp(self):
        account = AccountFactory(type=Account.Type.ASSET)
        txn = TransactionFactory(account=account, amount=Decimal("-1200.00"))
        journal_entry = JournalEntry.objects.create(
            date=datetime.date(2026, 1, 1), transaction=txn
        )
        self.item = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            account=account,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("1200.00"),
        )
        self.suggested = AccountFactory(type=Account.Type.EXPENSE)

    def _form(self, **overrides):
        data = {
            "accrued_journal_entry_item": str(self.item.id),
            "periods": "12",
            "description": "Annual insurance",
            "suggested_account": str(self.suggested.id),
        }
        data.update(overrides)
        return AmortizationForm(data=data)

    def test_valid_periods_accepted(self):
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)

    def test_blank_periods_is_a_validation_error_not_a_crash(self):
        """`periods < 1` on None raised TypeError, which is a 500 rather than
        a form error."""
        form = self._form(periods="")
        self.assertFalse(form.is_valid())
        self.assertIn("periods", form.errors)

    def test_missing_periods_key_is_a_validation_error(self):
        data = {
            "accrued_journal_entry_item": str(self.item.id),
            "description": "No periods at all",
            "suggested_account": str(self.suggested.id),
        }
        form = AmortizationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("periods", form.errors)

    def test_zero_periods_still_rejected(self):
        form = self._form(periods="0")
        self.assertFalse(form.is_valid())
        self.assertIn("periods", form.errors)
