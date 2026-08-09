"""Tests for the CSV Profiles Settings section HTMX views."""

from django.urls import reverse

from api.models import CSVProfile
from api.tests.test_helpers import HTMXViewTestCase
from api.tests.testing_factories import AccountFactory, CSVProfileFactory


def _post_data(**overrides):
    data = {
        "action": "save",
        "name": "Chase",
        "date": "Transaction Date",
        "description": "Description",
        "category": "Category",
        "inflow": "Amount",
        "outflow": "Amount",
        "date_format": "%Y-%m-%d",
        "clear_prepended_until_value": "",
    }
    data.update(overrides)
    return data


class CSVProfileSettingsViewTest(HTMXViewTestCase):
    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("settings-csv-profiles"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_panel_loads_and_lists_profiles(self):
        CSVProfileFactory(name="listedprofile")

        response = self.client.get(reverse("settings-csv-profiles"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "listedprofile")
        self.assertContains(response, "CSV Profiles")

    def test_new_profile_form_view(self):
        response = self.client.get(reverse("settings-csv-profile-new-form"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New CSV profile")
        self.assertNotContains(response, 'value="delete"')

    def test_profile_form_view_loads_profile(self):
        profile = CSVProfileFactory(name="editable")
        response = self.client.get(
            reverse("settings-csv-profile-form", args=[profile.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "editable")
        self.assertContains(response, 'value="delete"')

    def test_edit_form_prefills_existing_pairs(self):
        profile = CSVProfileFactory(name="haspairs")
        from api.models import CSVColumnValuePair

        pair = CSVColumnValuePair.objects.create(column="Status", value="Pending")
        profile.clear_values_column_pairs.set([pair])

        response = self.client.get(
            reverse("settings-csv-profile-form", args=[profile.id])
        )
        self.assertEqual(response.status_code, 200)
        # The pair is embedded for the Alpine editor to hydrate.
        self.assertContains(response, "Status")
        self.assertContains(response, "Pending")

    def test_create_profile(self):
        response = self.client.post(
            reverse("settings-csv-profiles"), data=_post_data(name="Ally")
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CSVProfile.objects.filter(name="Ally").exists())
        self.assertContains(response, "CSV profile created.")

    def test_create_profile_with_exclusion_pairs(self):
        data = _post_data(
            name="WithPairs",
            pair_column=["Status", "Type"],
            pair_value=["Pending", "Fee"],
        )
        response = self.client.post(reverse("settings-csv-profiles"), data=data)
        self.assertEqual(response.status_code, 200)

        profile = CSVProfile.objects.get(name="WithPairs")
        pairs = profile.clear_values_column_pairs.all()
        self.assertEqual(
            sorted((p.column, p.value) for p in pairs),
            [("Status", "Pending"), ("Type", "Fee")],
        )

    def test_missing_required_field_re_renders_with_error(self):
        data = _post_data(name="")
        response = self.client.post(reverse("settings-csv-profiles"), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CSVProfile.objects.exists())
        # Field preserved (echoed back) and no success alert.
        self.assertNotContains(response, "CSV profile created.")

    def test_lopsided_pair_reports_error(self):
        data = _post_data(
            name="BadPair",
            pair_column=["Status"],
            pair_value=[""],
        )
        response = self.client.post(reverse("settings-csv-profiles"), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CSVProfile.objects.filter(name="BadPair").exists())
        self.assertContains(response, "needs both a column and a value")

    def test_update_profile(self):
        profile = CSVProfileFactory(name="before")
        data = _post_data(name="after")
        response = self.client.post(
            reverse("settings-csv-profile", args=[profile.id]), data=data
        )
        self.assertEqual(response.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.name, "after")
        self.assertContains(response, "CSV profile updated.")

    def test_delete_profile(self):
        profile = CSVProfileFactory(name="goner")
        response = self.client.post(
            reverse("settings-csv-profile", args=[profile.id]),
            data={"action": "delete"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CSVProfile.objects.filter(id=profile.id).exists())
        self.assertContains(response, "CSV profile deleted.")

    def test_delete_linked_profile_shows_error(self):
        profile = CSVProfileFactory(name="linked")
        AccountFactory(csv_profile=profile)
        response = self.client.post(
            reverse("settings-csv-profile", args=[profile.id]),
            data={"action": "delete"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CSVProfile.objects.filter(id=profile.id).exists())
        self.assertContains(response, "still linked to an account")
