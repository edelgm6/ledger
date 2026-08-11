"""Tests for csv_profile_services — the Settings CRUD over CSVProfiles."""

from django.test import TestCase

from api.models import CSVColumnValuePair, CSVProfile
from api.services.csv_profile_services import (
    CSVProfileResult,
    delete_csv_profile,
    get_csv_profiles,
    save_csv_profile,
)
from api.tests.testing_factories import (
    AccountFactory,
    CSVColumnValuePairFactory,
    CSVProfileFactory,
)


def _cleaned_data(**overrides):
    """A full set of validated form fields for a CSV profile save."""
    data = {
        "name": "Chase",
        "date": "Transaction Date",
        "description": "Description",
        "category": "Category",
        "inflow": "Amount",
        "outflow": "Amount",
        "date_format": "%Y-%m-%d",
        "clear_prepended_until_value": "",
        "positive_outflows": False,
        "column_value_pairs": [],
    }
    data.update(overrides)
    return data


class GetCSVProfilesTest(TestCase):
    """Tests for get_csv_profiles() — the Settings list query."""

    def test_orders_by_name(self):
        CSVProfileFactory(name="charlie")
        CSVProfileFactory(name="alpha")
        CSVProfileFactory(name="bravo")

        names = [p.name for p in get_csv_profiles()]
        self.assertEqual(names, ["alpha", "bravo", "charlie"])

    def test_annotates_account_and_exclusion_counts(self):
        profile = CSVProfileFactory(name="counted")
        # Two accounts linked to this profile.
        AccountFactory(csv_profile=profile)
        AccountFactory(csv_profile=profile)
        # Two exclusion rules on this profile.
        CSVColumnValuePairFactory(
            csv_profile=profile, column="Status", value="Pending"
        )
        CSVColumnValuePairFactory(csv_profile=profile, column="Type", value="Fee")

        result = next(p for p in get_csv_profiles() if p.id == profile.id)
        self.assertEqual(result.account_count, 2)
        self.assertEqual(result.exclusion_count, 2)


class SaveCSVProfileTest(TestCase):
    """Tests for save_csv_profile() create/update including pair sync."""

    def test_creates_profile(self):
        result = save_csv_profile(_cleaned_data())

        self.assertIsInstance(result, CSVProfileResult)
        self.assertTrue(result.success)
        self.assertEqual(result.csv_profile.name, "Chase")
        self.assertEqual(result.csv_profile.date, "Transaction Date")
        self.assertEqual(CSVProfile.objects.count(), 1)

    def test_creates_profile_with_exclusion_pairs(self):
        result = save_csv_profile(
            _cleaned_data(
                column_value_pairs=[("Status", "Pending"), ("Type", "Fee")]
            )
        )

        self.assertTrue(result.success)
        pairs = result.csv_profile.clear_values_column_pairs.all()
        self.assertEqual(pairs.count(), 2)
        self.assertEqual(
            sorted((p.column, p.value) for p in pairs),
            [("Status", "Pending"), ("Type", "Fee")],
        )

    def test_unchecking_positive_outflows_clears_it(self):
        profile = save_csv_profile(
            _cleaned_data(positive_outflows=True)
        ).csv_profile

        result = save_csv_profile(
            _cleaned_data(positive_outflows=False), instance=profile
        )

        self.assertTrue(result.success)
        profile.refresh_from_db()
        self.assertFalse(profile.positive_outflows)

    def test_updates_profile_and_replaces_pairs(self):
        create = save_csv_profile(
            _cleaned_data(column_value_pairs=[("Status", "Pending")])
        )
        profile = create.csv_profile

        result = save_csv_profile(
            _cleaned_data(
                name="Chase Updated",
                column_value_pairs=[("Type", "Fee")],
            ),
            instance=profile,
        )

        self.assertTrue(result.success)
        profile.refresh_from_db()
        self.assertEqual(profile.name, "Chase Updated")
        pairs = profile.clear_values_column_pairs.all()
        self.assertEqual([(p.column, p.value) for p in pairs], [("Type", "Fee")])
        # The old pair is deleted, not orphaned.
        self.assertEqual(CSVColumnValuePair.objects.count(), 1)

    def test_clearing_pairs_removes_them(self):
        create = save_csv_profile(
            _cleaned_data(column_value_pairs=[("Status", "Pending")])
        )
        profile = create.csv_profile

        result = save_csv_profile(
            _cleaned_data(column_value_pairs=[]), instance=profile
        )

        self.assertTrue(result.success)
        self.assertEqual(profile.clear_values_column_pairs.count(), 0)
        self.assertEqual(CSVColumnValuePair.objects.count(), 0)


class DeleteCSVProfileTest(TestCase):
    """Tests for delete_csv_profile() including the PROTECT path."""

    def test_deletes_unlinked_profile(self):
        profile = CSVProfileFactory(name="deletable")

        result = delete_csv_profile(profile.id)

        self.assertTrue(result.success)
        self.assertFalse(CSVProfile.objects.filter(id=profile.id).exists())

    def test_delete_cascades_pairs(self):
        # The csv_profile FK is on_delete=CASCADE, so deleting the profile
        # removes its owned pairs at the database level (no manual cleanup).
        create = save_csv_profile(
            _cleaned_data(column_value_pairs=[("Status", "Pending")])
        )
        profile = create.csv_profile
        self.assertEqual(CSVColumnValuePair.objects.count(), 1)

        result = delete_csv_profile(profile.id)

        self.assertTrue(result.success)
        self.assertEqual(CSVColumnValuePair.objects.count(), 0)

    def test_cannot_delete_profile_linked_to_account(self):
        profile = CSVProfileFactory(name="in-use")
        AccountFactory(csv_profile=profile)

        result = delete_csv_profile(profile.id)

        self.assertFalse(result.success)
        self.assertIn("in-use", result.error)
        self.assertTrue(CSVProfile.objects.filter(id=profile.id).exists())

    def test_missing_profile_returns_not_found(self):
        result = delete_csv_profile(999999)

        self.assertFalse(result.success)
        self.assertEqual(result.error, "CSV profile not found.")
