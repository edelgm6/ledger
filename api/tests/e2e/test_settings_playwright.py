"""Playwright browser tests for the interactive Settings page.

Exercises the client-side behaviors: live search + count, row-select highlight,
the Type -> Sub-type dependent select, the New Account blank form, and create
re-rendering the list via HTMX.

Run:
    uv run python manage.py test api.tests.e2e.test_settings_playwright
"""
import os

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

from django.contrib.auth.models import User
from django.test import Client, LiveServerTestCase, tag
from playwright.sync_api import sync_playwright

from api.models import Account
from api.tests.testing_factories import AccountFactory, EntityFactory


@tag("e2e")
class SettingsSmokeTest(LiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        EntityFactory(name="Self")
        AccountFactory(name="Ally Checking", type=Account.Type.ASSET, sub_type=Account.SubType.CASH)
        AccountFactory(name="Dining", type=Account.Type.EXPENSE, sub_type=Account.SubType.OPERATING)
        AccountFactory(name="Federal Taxes", type=Account.Type.EXPENSE, sub_type=Account.SubType.TAX)
        self.context = self.browser.new_context()
        client = Client()
        client.force_login(self.user)
        sid = client.cookies["sessionid"].value
        self.context.add_cookies([{"name": "sessionid", "value": sid, "url": self.live_server_url}])
        self.page = self.context.new_page()

    def tearDown(self):
        self.page.close()
        self.context.close()

    def goto_settings(self):
        self.page.goto(self.live_server_url + "/settings/")
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_function("typeof Alpine !== 'undefined'")
        self.page.wait_for_selector(".set-table")

    def test_interactions(self):
        self.goto_settings()

        # Count label
        count = self.page.inner_text(".set-count")
        self.assertIn("3 accounts", count)

        # Search filters live + updates count
        self.page.fill(".set-search input", "ally")
        self.page.wait_for_timeout(150)
        self.assertIn("1 of 3", self.page.inner_text(".set-count"))
        visible = self.page.eval_on_selector_all(
            "tr.set-row",
            "els => els.filter(e => e.offsetParent !== null).map(e => e.querySelector('.set-td-name').innerText)",
        )
        self.assertEqual(visible, ["Ally Checking"])

        # Clear search, select a row -> form loads + row highlighted
        self.page.fill(".set-search input", "")
        with self.page.expect_response(lambda r: "/form/" in r.url):
            self.page.click("tr.set-row:has-text('Federal Taxes')")
        self.page.wait_for_selector(".set-form-header:has-text('Edit · Federal Taxes')")
        selected_name = self.page.inner_text("tr.set-row.selected .set-td-name")
        self.assertEqual(selected_name, "Federal Taxes")

        # Type -> Sub-type dependency: switch Type to Income, sub-type options change
        self.page.select_option("select[name='type']", "income")
        self.page.wait_for_timeout(100)
        sub_opts = self.page.eval_on_selector_all(
            "select[name='sub_type'] option", "els => els.map(e => e.value)"
        )
        self.assertIn("salary", sub_opts)
        self.assertNotIn("tax", sub_opts)

        # New Account -> blank create form
        with self.page.expect_response(lambda r: "new/form" in r.url):
            self.page.click("button:has-text('New Account')")
        self.page.wait_for_selector(".set-form-header:has-text('New account')")
        self.assertEqual(self.page.input_value(".set-input[name='name']"), "")

        # Create a new account -> appears in list, count grows
        self.page.fill(".set-input[name='name']", "New Brokerage")
        self.page.select_option("select[name='type']", "asset")
        with self.page.expect_response(lambda r: r.request.method == "POST"):
            self.page.click("button:has-text('Create')")
        self.page.wait_for_selector("tr.set-row:has-text('New Brokerage')")
        self.assertIn("4 accounts", self.page.inner_text(".set-count"))
        self.assertTrue(Account.objects.filter(name="New Brokerage").exists())
