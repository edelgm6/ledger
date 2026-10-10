"""The server is the single owner of which nav tab is highlighted.

The active class used to be set twice: by request.resolver_match conditionals
server-side, and by a jQuery click handler in base.html. They disagreed in
three ways -- opening the Financials dropdown stole the highlight, a failed
navigation still moved it (the handler fired on click, not on response), and a
hard load of a statements URL highlighted nothing at all, because the dropdown
had no server-side conditional.
"""

import re

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

# <li class="nav-item active"> ... <a ...>Label</a>
NAV_ITEM_RE = re.compile(
    r'<li class="nav-item([^"]*)"[^>]*>\s*(?:<a[^>]*>)?\s*([^<]*?)\s*<', re.S
)


class NavActiveTabTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="nav", password="p")
        self.client = Client()
        self.client.force_login(self.user)

    def active_labels(self, html):
        """Labels of the nav items currently carrying the active class."""
        return [
            label
            for classes, label in NAV_ITEM_RE.findall(html)
            if "active" in classes and label
        ]

    def test_each_page_highlights_exactly_one_tab(self):
        for url_name, label in [
            ("journal-entries", "Entries"),
            ("transactions", "Transactions"),
            ("taxes", "Taxes"),
            ("reconciliation", "Reconciliations"),
            ("amortization", "Amortizations"),
            ("recharacterize", "Recharacterize"),
            ("settings", "Settings"),
        ]:
            with self.subTest(url_name=url_name):
                html = self.client.get(reverse(url_name)).content.decode()
                self.assertEqual(
                    self.active_labels(html),
                    [label],
                    f"{url_name} should highlight exactly {label!r}",
                )

    def test_statements_highlight_the_financials_dropdown(self):
        """The regression: this highlighted nothing on a hard load, because the
        dropdown carried no server-side conditional and only the (click-driven)
        jQuery handler ever marked it."""
        for statement_type in ("income", "balance", "cash"):
            with self.subTest(statement_type=statement_type):
                html = self.client.get(
                    reverse("statements", args=[statement_type])
                ).content.decode()
                self.assertEqual(self.active_labels(html), ["Financials ▾"])

    def test_no_client_side_handler_competes_for_the_active_class(self):
        html = self.client.get(reverse("settings")).content.decode()
        self.assertNotIn(
            "removeClass('active')",
            html,
            "the jQuery handler must not reintroduce a second owner",
        )
        self.assertNotIn("addClass('active')", html)

    def test_boosted_navigation_re_renders_the_nav(self):
        """Without hx-select-oob the highlight would go stale on boosted
        navigation, since hx-select only swaps #container."""
        html = self.client.get(reverse("settings")).content.decode()
        self.assertIn('id="nav-links"', html)
        self.assertIn('hx-select-oob="#nav-links"', html)
