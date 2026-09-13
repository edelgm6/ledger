"""Every view must return a response when a submitted form is invalid.

These views used to fall through their `if form.is_valid():` block with no
else, so Django raised "didn't return an HttpResponse" (a 500) on any invalid
input. Two had sharper failure modes: ReconciliationView.post left
`reconciliations` unbound (UnboundLocalError) and read a missing
cleaned_data["date"] (KeyError), and the entity tag view read a missing
cleaned_data["entity"].

A 200 (or any handled status) is the assertion here -- the point is that bad
input is handled rather than crashing the request.
"""

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from api.models import (
    Account,
    Amortization,
    JournalEntryItem,
    Reconciliation,
    TaxCharge,
)
from api.tests.testing_factories import (
    AccountFactory,
    EntityFactory,
    JournalEntryFactory,
    TransactionFactory,
)

BAD_DATE = "not-a-date"


class InvalidFormHandlingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.client = Client()
        self.client.force_login(self.user)

    def assertNotServerError(self, response, label):
        self.assertLess(
            response.status_code,
            500,
            f"{label} returned {response.status_code} on invalid input",
        )

    def test_journal_entry_table_invalid_filter(self):
        resp = self.client.get(
            reverse("journal-entries-table"), {"filter-date_from": BAD_DATE}
        )
        self.assertNotServerError(resp, "JournalEntryTableView.get")

    def test_reconciliation_table_invalid_filter(self):
        resp = self.client.get(reverse("reconciliation-table"), {"date": BAD_DATE})
        self.assertNotServerError(resp, "ReconciliationTableView.get")

    def test_reconciliation_post_invalid_filter(self):
        """The plug branch never binds `reconciliations`, so an invalid filter
        form here used to raise UnboundLocalError before the KeyError could."""
        resp = self.client.post(reverse("reconciliation"), {"date": BAD_DATE})
        self.assertNotServerError(resp, "ReconciliationView.post")

    def test_reconciliation_post_plug_with_invalid_filter(self):
        account = AccountFactory(type=Account.Type.ASSET)
        rec = Reconciliation.objects.create(
            account=account, date=datetime.date(2026, 3, 31)
        )
        resp = self.client.post(
            reverse("reconciliation"), {"plug": rec.pk, "date": BAD_DATE}
        )
        self.assertNotServerError(resp, "ReconciliationView.post (plug branch)")

    def test_amortization_post_invalid_form(self):
        resp = self.client.post(reverse("amortization"), {"periods": "-1"})
        self.assertNotServerError(resp, "AmortizationView.post")

    def test_amortize_form_post_invalid_date(self):
        account = AccountFactory(type=Account.Type.ASSET)
        txn = TransactionFactory(account=account, amount=Decimal("-100.00"))
        journal_entry = JournalEntryFactory(transaction=txn)
        jei = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("100.00"),
            account=account,
        )
        amortization = Amortization.objects.create(
            accrued_journal_entry_item=jei,
            amount=Decimal("1200.00"),
            periods=12,
            description="Test amortization",
            suggested_account=account,
        )
        resp = self.client.post(
            reverse("amortize-form", args=[amortization.pk]), {"date": BAD_DATE}
        )
        self.assertNotServerError(resp, "AmortizeFormView.post")

    def test_index_wallet_post_invalid_form(self):
        resp = self.client.post(reverse("index"), {"amount": "not-a-number"})
        self.assertNotServerError(resp, "IndexView.post")

    def test_tag_entities_form_post_invalid_entity(self):
        account = AccountFactory(type=Account.Type.ASSET)
        txn = TransactionFactory(account=account, amount=Decimal("-100.00"))
        journal_entry = JournalEntryFactory(transaction=txn)
        jei = JournalEntryItem.objects.create(
            journal_entry=journal_entry,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("100.00"),
            account=account,
        )
        EntityFactory()
        resp = self.client.post(
            reverse("tag-entities-form", args=[jei.pk]), {"entity": "999999"}
        )
        self.assertNotServerError(resp, "TagEntitiesForm.post")

    def test_taxes_post_invalid_charge(self):
        resp = self.client.post(
            reverse("taxes"), {"amount": "not-a-number", "date": BAD_DATE}
        )
        self.assertNotServerError(resp, "TaxesView.post")

    def test_taxes_post_invalid_charge_surfaces_errors(self):
        """An invalid tax submission must not be silently discarded."""
        account = AccountFactory(
            tax_kind=Account.TaxKind.STATE, type=Account.Type.EXPENSE
        )
        payable = AccountFactory(
            type=Account.Type.LIABILITY, sub_type=Account.SubType.TAXES_PAYABLE
        )
        account.tax_payable_account = payable
        account.save()

        before = TaxCharge.objects.count()
        resp = self.client.post(
            reverse("taxes"),
            {"account": account.pk, "date": "2026-03-31", "amount": "not-a-number"},
        )
        self.assertNotServerError(resp, "TaxesView.post")
        self.assertEqual(
            TaxCharge.objects.count(), before, "invalid charge must not be saved"
        )
