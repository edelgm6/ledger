import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from api.models import Account, JournalEntryItem
from api.tests.testing_factories import (
    AccountFactory,
    EntityFactory,
    JournalEntryFactory,
    JournalEntryItemFactory,
    TransactionFactory,
)


class RecharacterizeViewsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.client.force_login(self.user)

        self.checking = AccountFactory(
            name="Ally Checking",
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH,
            is_closed=False,
        )
        self.groceries = AccountFactory(
            name="Groceries",
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.OPERATING,
            is_closed=False,
        )
        self.ally_bank = EntityFactory(name="Ally Bank")

        txn = TransactionFactory(
            description="Verizon", date=datetime.date(2025, 3, 1), is_closed=True
        )
        je = JournalEntryFactory(transaction=txn, date=txn.date)
        self.debit = JournalEntryItemFactory(
            journal_entry=je,
            account=self.checking,
            type=JournalEntryItem.JournalEntryType.DEBIT,
            amount=Decimal("50.00"),
        )

    def test_get_renders_page(self):
        resp = self.client.get(reverse("recharacterize"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Recharacterize")
        self.assertContains(resp, "recharacterize-main")
        # The manual builder renders with the shared typeahead-multiselect bound
        # to the account field (its <select multiple> lists the accounts).
        self.assertContains(resp, "Build an operation")
        self.assertContains(resp, 'name="account"')
        self.assertContains(resp, "ta-trigger")
        self.assertContains(resp, "Ally Checking")

    def test_reset_clears_session(self):
        resp = self.client.post(reverse("recharacterize-reset"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No changes proposed yet")

    def test_export_with_no_session_returns_header_only_csv(self):
        resp = self.client.get(reverse("recharacterize-export"), {"op": "0"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        body = resp.content.decode().strip().splitlines()
        self.assertEqual(len(body), 1)  # header only, no data rows

    def test_page_endpoint_with_no_session_renders_empty(self):
        resp = self.client.get(
            reverse("recharacterize-page"), {"op": "0", "page": "1"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No items to show")

    def test_history_panel_lists_applied_change_with_revert(self):
        from api.services.recharacterize_services import apply_operation

        ops = [
            {
                "filter": {"account": "Ally Checking", "entry_type": "debit"},
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]
        self.assertTrue(apply_operation(ops, 0).success)

        resp = self.client.get(reverse("recharacterize"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Recent changes")
        self.assertContains(resp, "Revert")

    def test_revert_endpoint_restores_and_marks_reverted(self):
        from api.models import RecharacterizeChange
        from api.services.recharacterize_services import apply_operation

        ops = [
            {
                "filter": {"account": "Ally Checking", "entry_type": "debit"},
                "action": {"type": "set_entity", "entity": "Ally Bank"},
            }
        ]
        result = apply_operation(ops, 0)
        self.debit.refresh_from_db()
        self.assertEqual(self.debit.entity, self.ally_bank)

        resp = self.client.post(
            reverse("recharacterize-revert") + f"?change={result.change_id}"
        )
        self.assertEqual(resp.status_code, 200)
        # The outcome is surfaced as a flash above the preview.
        self.assertContains(resp, "Reverted:")

        self.debit.refresh_from_db()
        self.assertIsNone(self.debit.entity)
        change = RecharacterizeChange.objects.get(id=result.change_id)
        self.assertTrue(change.is_reverted)

    def test_revert_invalid_change_reports_error(self):
        resp = self.client.post(reverse("recharacterize-revert") + "?change=999999")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "no longer exists")

    # --- manual builder -----------------------------------------------------

    def test_manual_adds_op_and_previews_it(self):
        # The account multi-select submits account PKs (typeahead-multiselect).
        resp = self.client.post(
            reverse("recharacterize-manual"),
            {
                "action_type": "set_entity",
                "account": self.checking.id,
                "entry_type": "debit",
                "target_entity": "Ally Bank",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "set entity")
        self.assertContains(resp, "Apply (1)")
        # A successful add returns to a fresh builder.
        self.assertContains(resp, "Build an operation")
        ops = self.client.session["recharacterize"]["operations"]
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["filter"]["account"], ["Ally Checking"])
        self.assertEqual(ops[0]["action"], {"type": "set_entity", "entity": "Ally Bank"})

    def test_new_ops_stack_on_top_newest_first(self):
        # Add op A (groceries), then op B (checking): B is newest and must sort to
        # the top of the plan (index 0) so it's the first one previewed.
        self.client.post(
            reverse("recharacterize-manual"),
            {"action_type": "clear_entity", "account": self.groceries.id},
        )
        self.client.post(
            reverse("recharacterize-manual"),
            {"action_type": "clear_entity", "account": self.checking.id},
        )
        ops = self.client.session["recharacterize"]["operations"]
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0]["filter"]["account"], ["Ally Checking"])  # newest
        self.assertEqual(ops[1]["filter"]["account"], ["Groceries"])  # oldest
        # Editing op 0 overwrites in place — it does not jump position.
        resp = self.client.post(
            reverse("recharacterize-manual"),
            {"op": "0", "action_type": "clear_entity", "entry_type": "debit"},
        )
        self.assertEqual(resp.status_code, 200)
        ops = self.client.session["recharacterize"]["operations"]
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0]["filter"], {"entry_type": "debit"})
        self.assertEqual(ops[1]["filter"]["account"], ["Groceries"])

    def test_manual_then_apply_updates_items_records_history_and_flashes(self):
        from api.models import RecharacterizeChange

        self.client.post(
            reverse("recharacterize-manual"),
            {
                "action_type": "set_entity",
                "account": self.checking.id,
                "entry_type": "debit",
                "target_entity": "Ally Bank",
            },
        )
        resp = self.client.post(reverse("recharacterize-apply") + "?op=0")
        self.assertEqual(resp.status_code, 200)
        # The apply outcome is surfaced as a flash above the preview.
        self.assertContains(resp, "Updated 1 journal entry item")
        self.debit.refresh_from_db()
        self.assertEqual(self.debit.entity, self.ally_bank)
        self.assertTrue(RecharacterizeChange.objects.exists())
        # The applied operation is removed from the plan.
        self.assertEqual(self.client.session["recharacterize"]["operations"], [])

    def test_apply_one_operation_leaves_the_rest(self):
        EntityFactory(name="Other Bank")
        # op A (oldest) targets Other Bank; op B (newest, index 0) targets Ally Bank.
        self.client.post(
            reverse("recharacterize-manual"),
            {
                "action_type": "set_entity",
                "account": self.checking.id,
                "entry_type": "debit",
                "target_entity": "Other Bank",
            },
        )
        self.client.post(
            reverse("recharacterize-manual"),
            {
                "action_type": "set_entity",
                "account": self.checking.id,
                "entry_type": "debit",
                "target_entity": "Ally Bank",
            },
        )

        # Apply only operation 0 (Ally Bank); operation 1 must survive.
        resp = self.client.post(reverse("recharacterize-apply") + "?op=0")
        self.assertEqual(resp.status_code, 200)
        self.debit.refresh_from_db()
        self.assertEqual(self.debit.entity, self.ally_bank)
        remaining = self.client.session["recharacterize"]["operations"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["action"]["entity"], "Other Bank")

    def test_apply_error_surfaces_flash_error(self):
        # A blocked op (no criteria) can't be applied; the error is surfaced.
        self.client.post(
            reverse("recharacterize-manual"), {"action_type": "clear_entity"}
        )
        resp = self.client.post(reverse("recharacterize-apply") + "?op=0")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "alert-danger")
        # The op stays in the plan since nothing was applied.
        self.assertEqual(
            len(self.client.session["recharacterize"]["operations"]), 1
        )

    def test_manual_invalid_date_shows_error_and_adds_no_op(self):
        resp = self.client.post(
            reverse("recharacterize-manual"),
            {
                "action_type": "clear_entity",
                "account": self.checking.id,
                "date_from": "not-a-date",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "date_from")
        # The invalid submit never writes the plan, so no op is added.
        state = self.client.session.get("recharacterize", {"operations": []})
        self.assertEqual(state["operations"], [])

    def test_manual_empty_filter_shows_blocked_op_in_preview(self):
        # A no-criteria op is valid form input but blocked by the guardrails,
        # surfaced inline in the preview — not a hard error.
        resp = self.client.post(
            reverse("recharacterize-manual"), {"action_type": "clear_entity"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "no criteria")
        self.assertEqual(
            len(self.client.session["recharacterize"]["operations"]), 1
        )

    def _seed_view_op(self):
        """Adds one manual view op over the matching checking debits."""
        return self.client.post(
            reverse("recharacterize-manual"),
            {
                "action_type": "view",
                "account": self.checking.id,
                "entry_type": "debit",
            },
        )

    def test_view_op_shows_export_link_and_no_apply(self):
        resp = self._seed_view_op()
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Export all")
        self.assertNotContains(resp, "Apply (")  # view-only: no Apply button

    def test_export_streams_csv_of_matched_items(self):
        # Populate the session with a view operation over the matching debit.
        self._seed_view_op()

        resp = self.client.get(reverse("recharacterize-export"), {"op": "0"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("attachment", resp["Content-Disposition"])
        body = resp.content.decode()
        self.assertIn("Account Before", body)  # header row
        self.assertIn("Ally Checking", body)  # the matched item

    def test_page_endpoint_returns_paginated_fragment(self):
        # 30 matching debits so the preview sample (25) has more to expand.
        for i in range(30):
            txn = TransactionFactory(
                description=f"Verizon {i}",
                date=datetime.date(2025, 4, 1),
                is_closed=True,
            )
            je = JournalEntryFactory(transaction=txn, date=txn.date)
            JournalEntryItemFactory(
                journal_entry=je,
                account=self.checking,
                type=JournalEntryItem.JournalEntryType.DEBIT,
                amount=Decimal("10.00"),
            )
        resp = self._seed_view_op()
        # With >1 page the preview shows the pager inline (no "View all" gate).
        self.assertContains(resp, "Page 1 of")
        self.assertContains(resp, "Next")
        self.assertContains(resp, reverse("recharacterize-page"))

        # Page 1 fragment paginates with a Next control.
        resp = self.client.get(
            reverse("recharacterize-page"), {"op": "0", "page": "1"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "affected-region-0")
        self.assertContains(resp, "Page 1 of")
        self.assertContains(resp, "Next")

    # --- editing one operation in place ------------------------------------

    def _seed_op(self):
        """Adds one manual set-entity op to the session and returns the response."""
        return self.client.post(
            reverse("recharacterize-manual"),
            {
                "action_type": "set_entity",
                "description_contains": "Verizon",
                "account": self.checking.id,
                "entry_type": "debit",
                "target_entity": "Ally Bank",
            },
        )

    def test_edit_prefills_the_builder(self):
        self._seed_op()
        resp = self.client.get(reverse("recharacterize-edit") + "?op=0")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Editing operation 1")
        # The filter is prefilled from the stored op.
        self.assertContains(resp, 'value="Verizon"')
        self.assertContains(resp, "Save changes")
        # A hidden op index makes the next save overwrite rather than append.
        self.assertContains(resp, 'name="op"')
        # The account multi-select and the target entity render as selected (the
        # string-PK initial is what makes the typeahead mark its option selected).
        self.assertContains(
            resp, f'<option value="{self.checking.id}" selected>Ally Checking</option>'
        )
        self.assertContains(resp, '<option value="Ally Bank" selected>')

    def test_edit_save_overwrites_not_appends(self):
        self._seed_op()
        resp = self.client.post(
            reverse("recharacterize-manual"),
            {
                "op": "0",
                "action_type": "clear_entity",
                "account": self.checking.id,
            },
        )
        self.assertEqual(resp.status_code, 200)
        ops = self.client.session["recharacterize"]["operations"]
        # Still one op, but its action was overwritten.
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["action"], {"type": "clear_entity"})

    def test_cancel_returns_to_fresh_builder(self):
        self._seed_op()
        resp = self.client.get(reverse("recharacterize-edit"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Build an operation")
        self.assertNotContains(resp, "Editing operation")
        # The plan is untouched by entering/leaving edit mode.
        self.assertEqual(
            len(self.client.session["recharacterize"]["operations"]), 1
        )
