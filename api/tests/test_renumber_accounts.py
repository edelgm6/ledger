"""Tests for the renumber_accounts management command.

The command maps by numeric prefix only, so these use synthetic labels.
"""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from api.models import Account
from api.tests.testing_factories import AccountFactory


class RenumberAccountsTest(TestCase):
    def _run(self, **kwargs):
        out = StringIO()
        call_command("renumber_accounts", stdout=out, **kwargs)
        return out.getvalue()

    def test_rewrites_prefix_and_preserves_label(self):
        account = AccountFactory(name="1000-Checking Account")
        self._run()
        account.refresh_from_db()
        self.assertEqual(account.name, "1010-Checking Account")

    def test_preserves_labels_with_punctuation(self):
        account = AccountFactory(name="5420-Food, Fuel, Fun")
        self._run()
        account.refresh_from_db()
        # 5420 is unchanged in the map; the comma-laden label survives intact.
        self.assertEqual(account.name, "5420-Food, Fuel, Fun")

    def test_handles_colliding_targets_without_integrity_error(self):
        # 4020 -> 4100 while 4100 -> 4400: the intermediate 4100 collides with a
        # still-existing account, which the two-phase rename must absorb.
        first = AccountFactory(name="4020-Account One")
        second = AccountFactory(
            name="4100-Account Two",
            special_type=Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES,
        )
        self._run()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.name, "4100-Account One")
        self.assertEqual(second.name, "4400-Account Two")
        # special_type is left untouched by the rename.
        self.assertEqual(
            second.special_type,
            Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES,
        )

    def test_rebands_account_into_correct_band(self):
        account = AccountFactory(name="1311-Holding")
        self._run()
        account.refresh_from_db()
        self.assertEqual(account.name, "1560-Holding")

    def test_unknown_prefix_aborts_without_writing(self):
        valid = AccountFactory(name="1000-Checking Account")
        AccountFactory(name="9999-Unmapped Account")
        with self.assertRaises(CommandError):
            self._run()
        valid.refresh_from_db()
        self.assertEqual(valid.name, "1000-Checking Account")

    def test_name_without_prefix_aborts(self):
        AccountFactory(name="No Prefix Here")
        with self.assertRaises(CommandError):
            self._run()

    def test_dry_run_writes_nothing(self):
        account = AccountFactory(name="1000-Checking Account")
        output = self._run(dry_run=True)
        account.refresh_from_db()
        self.assertEqual(account.name, "1000-Checking Account")
        self.assertIn("Dry run", output)
        self.assertIn("1000-Checking Account  ->  1010-Checking Account", output)
