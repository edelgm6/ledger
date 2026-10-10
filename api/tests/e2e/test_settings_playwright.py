"""Playwright browser tests for the interactive Settings page.

Exercises the client-side behaviors: live search + count, row-select highlight,
the Type -> Sub-type dependent select, the New Account blank form, and create
re-rendering the list via HTMX.

Waits go through PlaywrightTestCase, which blocks on the condition each
assertion depends on rather than on network quiet or a fixed sleep. See
api/tests/e2e/playwright_base.py.

Run:
    uv run python manage.py test api.tests.e2e.test_settings_playwright
"""

from django.contrib.auth.models import User
from django.test import Client

from api.models import Account
from api.tests.e2e.playwright_base import PlaywrightTestCase
from api.tests.testing_factories import AccountFactory, EntityFactory


class SettingsSmokeTest(PlaywrightTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        EntityFactory(name="Self")
        AccountFactory(name="Ally Checking", type=Account.Type.ASSET, sub_type=Account.SubType.CASH)
        AccountFactory(name="Dining", type=Account.Type.EXPENSE, sub_type=Account.SubType.OPERATING)
        AccountFactory(name="Federal Taxes", type=Account.Type.EXPENSE, sub_type=Account.SubType.TAX)
        client = Client()
        client.force_login(self.user)
        sid = client.cookies["sessionid"].value
        self.context.add_cookies(
            [{"name": "sessionid", "value": sid, "url": self.live_server_url}]
        )

    def goto_settings(self):
        self.goto("/settings/")
        self.page.wait_for_selector(".table")

    def test_interactions(self):
        self.goto_settings()

        # Count label
        count = self.page.inner_text(".card-count")
        self.assertIn("3 accounts", count)

        # Search filters live + updates count
        self.page.fill(".search input", "ally")
        # Wait on the row visibility this asserts, not on the live count: they
        # are separate Alpine effects and the count settles first, so waiting
        # on the count can observe "1 of 3" while all three rows are still
        # shown.
        self.wait_for_visible_text("tr.row", ["Ally Checking"])
        self.assertEqual(self.visible_text("tr.row"), ["Ally Checking"])
        self.assertIn("1 of 3", self.page.inner_text(".card-count"))

        # Clear search, select a row -> form loads + row highlighted
        self.page.fill(".search input", "")
        with self.page.expect_response(lambda r: "/form/" in r.url):
            self.page.click("tr.row:has-text('Federal Taxes')")
        self.page.wait_for_selector(".form-header:has-text('Edit · Federal Taxes')")
        # `selected` is an Alpine-bound class, so wait for it rather than
        # assuming it has been applied by the time the form arrives.
        self.page.wait_for_selector("tr.row.selected")
        selected_name = self.page.inner_text("tr.row.selected .td-name")
        self.assertEqual(selected_name, "Federal Taxes")

        # Sub-type preselects the saved value, not the first option for the type
        self.assertEqual(self.page.input_value("select[name='sub_type']"), "tax")

        # Type -> Sub-type dependency: switch Type to Income, sub-type options change
        self.page.select_option("select[name='type']", "income")
        # Wait for the dependent select to actually be rebuilt.
        self.wait_for_option_values(
            "select[name='sub_type']", includes=["salary"], excludes=["tax"]
        )

        # New Account -> blank create form
        with self.page.expect_response(lambda r: "new/form" in r.url):
            self.page.click("button:has-text('New Account')")
        self.page.wait_for_selector(".form-header:has-text('New account')")
        self.assertEqual(self.page.input_value(".input[name='name']"), "")

        # Create a new account -> appears in list, count grows
        self.page.fill(".input[name='name']", "New Brokerage")
        self.page.select_option("select[name='type']", "asset")
        with self.page.expect_response(lambda r: r.request.method == "POST"):
            self.page.click("button:has-text('Create')")
        self.page.wait_for_selector("tr.row:has-text('New Brokerage')")
        self.wait_for_htmx()
        self.wait_for_text(".card-count", "4 accounts")
        self.assertTrue(Account.objects.filter(name="New Brokerage").exists())
