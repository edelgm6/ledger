"""End-to-end coverage of the statement HTML rendering path.

These are characterization tests. The statement pages had no test coverage at
all, and the riskiest refactor waiting on them -- passing the typed
StatementSummary to the templates instead of flattening it into dicts --
fails *silently*: a missed attribute path renders an empty table rather than
raising. So every assertion here pairs an account name with the amount next to
it in the rendered row, and the structural assertions require a minimum number
of rows. A table that silently empties fails these tests.

Each test drives the real stack: view -> service -> helper -> template.
"""

import datetime
import re
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from api.models import Entity
from api.tests.scenario_builders import (
    create_chart_of_accounts,
    create_multi_line_journal_entry,
)

FROM_DATE = datetime.date(2026, 3, 1)
TO_DATE = datetime.date(2026, 3, 31)

# <td class="td-name">Groceries</td><td class="right">$300</td>
ROW_RE = re.compile(
    r'<td class="td-name">\s*([^<]*?)\s*</td>\s*'
    r'<td class="right">\s*\$([^<]*?)\s*</td>',
    re.S,
)
# The sub_type subtotal rows (bold) inside each section.
SUBTOTAL_RE = re.compile(
    r'<td class="td-strong">\s*([^<]*?)\s*</td>\s*'
    r'<td class="right td-strong">\s*\$([^<]*?)\s*</td>',
    re.S,
)
HEADING_RE = re.compile(r"<h4>\s*([^<]*?)\s*</h4>", re.S)


class StatementRenderingTestCase(TestCase):
    """A small but complete ledger: salary in, groceries out, one entity."""

    @classmethod
    def setUpTestData(cls):
        coa = create_chart_of_accounts()
        cls.accounts = coa["accounts"]
        cls.special = coa["special"]
        cls.employer = Entity.objects.create(name="Employer Inc")

        create_multi_line_journal_entry(
            date=datetime.date(2026, 3, 10),
            entries=[
                {
                    "account": cls.accounts["checking"],
                    "type": "debit",
                    "amount": Decimal("5000.00"),
                    "entity": cls.employer,
                },
                {
                    "account": cls.accounts["salary"],
                    "type": "credit",
                    "amount": Decimal("5000.00"),
                    "entity": cls.employer,
                },
            ],
            description="March salary",
        )
        create_multi_line_journal_entry(
            date=datetime.date(2026, 3, 15),
            entries=[
                {
                    "account": cls.accounts["groceries"],
                    "type": "debit",
                    "amount": Decimal("300.00"),
                },
                {
                    "account": cls.accounts["checking"],
                    "type": "credit",
                    "amount": Decimal("300.00"),
                },
            ],
            description="Groceries",
        )

    def setUp(self):
        self.user = User.objects.create_user(username="statements", password="p")
        self.client = Client()
        self.client.force_login(self.user)

    # --- helpers ---------------------------------------------------------

    def get_statement(self, statement_type, **params):
        query = {
            "date_from": FROM_DATE.isoformat(),
            "date_to": TO_DATE.isoformat(),
        }
        query.update(params)
        response = self.client.get(
            reverse("statements", args=[statement_type]), query
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    @staticmethod
    def rows(html):
        """{account name -> amount string} for the ordinary statement rows."""
        return {name: amount for name, amount in ROW_RE.findall(html)}

    @staticmethod
    def subtotals(html):
        """{sub_type name -> amount string} for the bold subtotal rows."""
        return {name: amount for name, amount in SUBTOTAL_RE.findall(html)}

    @staticmethod
    def headings(html):
        return [h for h in HEADING_RE.findall(html)]

    def assertRow(self, html, name, amount):
        """The row must exist *and* carry the expected amount.

        Asserting the pair is the point: a broken attribute path drops the row
        entirely, and asserting only on the name would still pass if the
        template rendered the label from somewhere else.
        """
        rows = self.rows(html)
        self.assertIn(
            name, rows, f"no row for {name!r}; rendered rows: {sorted(rows)}"
        )
        self.assertEqual(
            rows[name], amount, f"{name!r} rendered ${rows[name]}, expected ${amount}"
        )


class IncomeStatementRenderingTest(StatementRenderingTestCase):
    """Income statement grouped by account (the default)."""

    def test_section_headings_carry_their_totals(self):
        html = self.get_statement("income")
        headings = self.headings(html)
        self.assertIn("Net Income: $4,700", headings)
        self.assertIn("Income: $5,000", headings)
        self.assertIn("Expenses: $300", headings)

    def test_equity_section_renders_through_the_summary(self):
        """summary.equity.balances -> account.balances -> balance.account.

        This is one of the two blocks that reads through the flattened summary,
        so it is exactly what breaks if that flattening changes shape.
        """
        html = self.get_statement("income")
        self.assertRow(html, "Realized Net Income", "4,700")
        self.assertRow(html, "Unrealized Gains/Losses", "0")

    def test_expense_section_renders_subtotals_and_rows(self):
        """The other summary-driven block: a sub_type subtotal plus its rows."""
        html = self.get_statement("income")
        self.assertEqual(self.subtotals(html).get("Operating"), "300")
        self.assertRow(html, "Groceries", "300")

    def test_income_rows_render_with_amounts(self):
        html = self.get_statement("income")
        self.assertRow(html, "Salary", "5,000")

    def test_expense_section_is_not_empty(self):
        """A silently empty table is the failure mode being guarded against."""
        html = self.get_statement("income")
        self.assertGreaterEqual(
            len(self.rows(html)),
            10,
            "the statement rendered far too few rows -- a section is empty",
        )
        self.assertGreaterEqual(len(self.subtotals(html)), 3)

    def test_expense_rows_link_to_their_drill_down(self):
        """Expense rows are clickable; the link carries the account id."""
        html = self.get_statement("income")
        groceries = self.accounts["groceries"]
        self.assertIn(
            reverse("statement-detail", args=[groceries.id]),
            html,
            "the Groceries row lost its drill-down link",
        )


class IncomeStatementByEntityRenderingTest(StatementRenderingTestCase):
    """Income statement grouped by entity -- a different summary dataclass."""

    def test_entity_rows_render_with_amounts(self):
        html = self.get_statement("income", group_by="entity")
        self.assertRow(html, "Employer Inc", "5,000")

    def test_untagged_items_group_under_unassigned(self):
        html = self.get_statement("income", group_by="entity")
        self.assertRow(html, "Unassigned", "300")

    def test_subtotals_render_by_sub_type(self):
        html = self.get_statement("income", group_by="entity")
        subtotals = self.subtotals(html)
        self.assertEqual(subtotals.get("Salary"), "5,000")
        self.assertEqual(subtotals.get("Operating"), "300")

    def test_headings_match_the_by_account_view(self):
        """Grouping changes the rows, not the section totals."""
        by_entity = self.headings(self.get_statement("income", group_by="entity"))
        by_account = self.headings(self.get_statement("income"))
        self.assertEqual(by_entity, by_account)


class BalanceSheetRenderingTest(StatementRenderingTestCase):
    """Every section of the balance sheet reads through the summary."""

    def test_section_headings_carry_their_totals(self):
        html = self.get_statement("balance")
        headings = self.headings(html)
        self.assertIn("Assets: $4,700", headings)
        self.assertIn("Liabilities: $0", headings)
        self.assertIn("Equity: $4,700", headings)

    def test_asset_rows_render_with_amounts(self):
        html = self.get_statement("balance")
        self.assertRow(html, "Checking Account", "4,700")

    def test_sub_type_subtotals_render(self):
        html = self.get_statement("balance")
        self.assertEqual(self.subtotals(html).get("Cash"), "4,700")

    def test_all_three_sections_are_populated(self):
        """Assets, liabilities and equity each render their sub_type groups."""
        html = self.get_statement("balance")
        subtotals = self.subtotals(html)
        for expected in ("Cash", "Short-term Debt", "Retained Earnings"):
            self.assertIn(
                expected,
                subtotals,
                f"the {expected!r} group is missing -- a section rendered empty",
            )

    def test_balance_sheet_balances(self):
        """Assets == Liabilities + Equity, as rendered."""
        headings = {
            h.split(":")[0]: h.split("$")[1] for h in self.headings(self.get_statement("balance"))
        }
        self.assertEqual(headings["Assets"], "4,700")
        self.assertEqual(headings["Liabilities"], "0")
        self.assertEqual(headings["Equity"], "4,700")


class CashFlowStatementRenderingTest(StatementRenderingTestCase):
    def test_section_subtotals_render(self):
        html = self.get_statement("cash")
        subtotals = self.subtotals(html)
        self.assertEqual(subtotals.get("Cash from Operations"), "4,700")
        self.assertIn("Cash from Financing", subtotals)
        self.assertIn("Cash from Investing", subtotals)

    def test_operations_rows_render_with_amounts(self):
        html = self.get_statement("cash")
        self.assertRow(html, "Realized Net Income", "4,700")

    def test_is_not_empty(self):
        html = self.get_statement("cash")
        self.assertGreaterEqual(len(self.rows(html)), 5)


class StatementDetailRenderingTest(StatementRenderingTestCase):
    """The drill-down fragment loaded when a statement row is clicked."""

    def test_account_detail_lists_its_journal_entry_items(self):
        groceries = self.accounts["groceries"]
        response = self.client.get(
            reverse("statement-detail", args=[groceries.id]),
            {"from_date": FROM_DATE.isoformat(), "to_date": TO_DATE.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("Groceries", html)
        self.assertIn("300", html)

    def test_detail_for_an_account_with_no_activity_still_renders(self):
        dining = self.accounts["dining"]
        response = self.client.get(
            reverse("statement-detail", args=[dining.id]),
            {"from_date": FROM_DATE.isoformat(), "to_date": TO_DATE.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
