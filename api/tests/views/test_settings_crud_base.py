"""Guards the shared Settings CRUD base view.

Six sections' POST handlers were byte-identical apart from four names, so they
now share SettingsCrudView. Two things about that consolidation can regress
silently, and both are asserted here:

- Authentication. LoginRequiredMixin moved from the six subclasses onto the
  base. If it were dropped there, every one of these endpoints would quietly
  become public.
- The noun wiring. Each subclass declares one `noun` used for *both* the
  service Result's object attribute and the `_render_content` keyword. A typo
  would surface as a silently empty fragment rather than an error.
"""

from django.test import TestCase
from django.urls import reverse

from api.views.autotag_settings_views import AutoTagSettingsView
from api.views.bill_settings_views import BillRulesView
from api.views.csv_settings_views import CSVProfileSettingsView
from api.views.entity_settings_views import EntitySettingsView
from api.views.prefill_settings_views import PrefillSettingsView
from api.views.settings_crud import SettingsCrudView
from api.views.settings_views import SettingsView

CRUD_VIEWS = [
    SettingsView,
    EntitySettingsView,
    AutoTagSettingsView,
    CSVProfileSettingsView,
    PrefillSettingsView,
    BillRulesView,
]

# (url name, the pk kwarg the route captures)
CRUD_ROUTES = [
    ("settings", "account_id"),
    ("settings-entities", "entity_id"),
    ("settings-autotags", "autotag_id"),
    ("settings-csv-profiles", "csv_profile_id"),
    ("settings-prefills", "prefill_id"),
    ("settings-bill-rules", "rule_id"),
]


class SettingsCrudBaseTest(TestCase):
    def test_all_six_sections_use_the_shared_base(self):
        for view in CRUD_VIEWS:
            with self.subTest(view=view.__name__):
                self.assertTrue(issubclass(view, SettingsCrudView))

    def test_every_section_declares_its_four_names(self):
        for view in CRUD_VIEWS:
            with self.subTest(view=view.__name__):
                self.assertTrue(view.noun, "noun must be declared")
                self.assertIsNotNone(view.model, "model must be declared")
                self.assertIsNotNone(view.form_class, "form_class must be declared")
                self.assertTrue(view.pk_url_kwarg, "pk_url_kwarg must be declared")

    def test_declared_noun_matches_the_render_content_signature(self):
        """The noun is passed as a keyword to each section's _render_content,
        so a mismatch would raise at render time -- or worse, be swallowed by
        a **kwargs signature."""
        import inspect

        for view in CRUD_VIEWS:
            with self.subTest(view=view.__name__):
                params = inspect.signature(view._render_content).parameters
                self.assertIn(
                    view.noun,
                    params,
                    f"{view.__name__}._render_content has no {view.noun!r} "
                    "parameter, so the declared noun is wrong",
                )

    def test_declared_pk_kwarg_matches_the_route(self):
        """pk_url_kwarg must match what the URL conf actually captures, or the
        base reads None and every edit silently becomes a create."""
        from django.urls import get_resolver

        resolver = get_resolver()
        for view, (url_name, expected_kwarg) in zip(CRUD_VIEWS, CRUD_ROUTES):
            with self.subTest(view=view.__name__):
                self.assertEqual(view.pk_url_kwarg, expected_kwarg)
                # And the route by that name resolves.
                self.assertTrue(resolver.reverse_dict.get(url_name))

    def test_every_section_requires_authentication(self):
        """LoginRequiredMixin lives on the base now. If it were removed there,
        all six endpoints would become public at once."""
        for url_name, _ in CRUD_ROUTES:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(
                    response.status_code, 302, f"{url_name} did not redirect"
                )
                self.assertIn("/login/", response.url)

    def test_post_also_requires_authentication(self):
        for url_name, _ in CRUD_ROUTES:
            with self.subTest(url_name=url_name):
                response = self.client.post(reverse(url_name), {"name": "x"})
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response.url)
