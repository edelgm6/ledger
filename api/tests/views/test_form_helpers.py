"""Unit tests for resolve_form_values — the shared Settings-form value resolver."""

import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase

from api.views.form_helpers import resolve_form_values


class _BoundForm:
    """Minimal stand-in for a bound Django form (only what the helper reads)."""

    is_bound = True

    def __init__(self, data):
        self.data = data


class ResolveFormValuesBoundTest(SimpleTestCase):
    """Bound form present: echo submitted data (re-display an invalid POST)."""

    def test_text_uses_submitted_value_then_default(self):
        form = _BoundForm({"name": "typed"})
        values = resolve_form_values(
            None, form, text=("name", "type"), defaults={"type": "asset"}
        )
        self.assertEqual(values["name"], "typed")
        # Missing key falls back to the provided default.
        self.assertEqual(values["type"], "asset")

    def test_fk_uses_submitted_value_and_ignores_defaults(self):
        form = _BoundForm({"account": "5"})
        values = resolve_form_values(
            None, form, fks=("account", "entity"), defaults={"account": "9"}
        )
        self.assertEqual(values["account"], "5")
        # An FK always defaults to "" regardless of `defaults`.
        self.assertEqual(values["entity"], "")

    def test_boolean_reflects_presence_in_post(self):
        form = _BoundForm({"is_closed": "on"})
        values = resolve_form_values(
            None, form, booleans=("is_closed", "is_depreciation")
        )
        self.assertTrue(values["is_closed"])
        self.assertFalse(values["is_depreciation"])

    def test_date_uses_submitted_string(self):
        form = _BoundForm({"start_date": "2026-01-02"})
        values = resolve_form_values(None, form, dates=("start_date",))
        self.assertEqual(values["start_date"], "2026-01-02")


class ResolveFormValuesInstanceTest(SimpleTestCase):
    """No bound form, instance present: show the stored values."""

    def _instance(self, **kwargs):
        return SimpleNamespace(**kwargs)

    def test_text_none_renders_empty(self):
        inst = self._instance(keyword=None, name="Gross")
        values = resolve_form_values(inst, None, text=("keyword", "name"))
        self.assertEqual(values["keyword"], "")
        self.assertEqual(values["name"], "Gross")

    def test_fk_renders_string_id_or_empty(self):
        inst = self._instance(account_id=7, entity_id=None)
        values = resolve_form_values(inst, None, fks=("account", "entity"))
        self.assertEqual(values["account"], "7")
        self.assertEqual(values["entity"], "")

    def test_date_renders_isoformat_or_empty(self):
        inst = self._instance(
            start_date=datetime.date(2026, 7, 1), end_date=None
        )
        values = resolve_form_values(inst, None, dates=("start_date", "end_date"))
        self.assertEqual(values["start_date"], "2026-07-01")
        self.assertEqual(values["end_date"], "")

    def test_boolean_reads_attribute(self):
        inst = self._instance(is_closed=True)
        values = resolve_form_values(inst, None, booleans=("is_closed",))
        self.assertTrue(values["is_closed"])

    def test_unbound_form_is_treated_as_absent(self):
        # An unbound form (create page) should not shadow the instance branch.
        class Unbound:
            is_bound = False

        inst = self._instance(name="Edited")
        values = resolve_form_values(inst, Unbound(), text=("name",))
        self.assertEqual(values["name"], "Edited")


class ResolveFormValuesBlankTest(SimpleTestCase):
    """Neither form nor instance: blank-create defaults."""

    def test_defaults_and_empties(self):
        values = resolve_form_values(
            None,
            None,
            text=("name", "type", "date_window_days"),
            fks=("entity",),
            booleans=("is_closed", "wants_email"),
            defaults={
                "type": "asset",
                "date_window_days": "7",
                "wants_email": True,
            },
        )
        self.assertEqual(values["name"], "")
        self.assertEqual(values["type"], "asset")
        self.assertEqual(values["date_window_days"], "7")
        self.assertEqual(values["entity"], "")
        self.assertFalse(values["is_closed"])
        self.assertTrue(values["wants_email"])
