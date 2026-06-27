"""Tests for the Entities Settings section HTMX views."""

from django.urls import reverse

from api.models import Entity
from api.tests.test_helpers import HTMXViewTestCase
from api.tests.testing_factories import (
    AccountFactory,
    EntityFactory,
    LoanFactory,
)


class EntitySettingsViewTest(HTMXViewTestCase):
    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("settings-entities"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_panel_loads_and_lists_entities(self):
        entity = EntityFactory(name="Listed Entity")
        # Two accounts default to this entity -> account count of 2.
        AccountFactory(entity=entity)
        AccountFactory(entity=entity)

        response = self.client.get(reverse("settings-entities"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Listed Entity")
        self.assertContains(response, "Entities")
        # The account count column is rendered.
        self.assertContains(response, "2 accounts")
        # The 90-day tag usage column is rendered and sortable.
        self.assertContains(response, "Tags (90d)")
        self.assertContains(response, 'data-sort-t90')

    def test_new_entity_form_view(self):
        response = self.client.get(reverse("settings-entity-new-form"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New entity")
        # No Delete button on a blank create form.
        self.assertNotContains(response, 'value="delete"')

    def test_entity_form_view_loads_entity(self):
        entity = EntityFactory(name="Editable Entity")
        response = self.client.get(
            reverse("settings-entity-form", args=[entity.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editable Entity")
        self.assertContains(response, 'value="delete"')

    def test_create_entity(self):
        data = {"action": "save", "name": "New Bank", "is_closed": ""}
        response = self.client.post(reverse("settings-entities"), data=data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Entity.objects.filter(name="New Bank").exists())
        self.assertContains(response, "Entity created.")

    def test_create_closed_entity(self):
        data = {"action": "save", "name": "Closed Co", "is_closed": "on"}
        response = self.client.post(reverse("settings-entities"), data=data)
        self.assertEqual(response.status_code, 200)
        entity = Entity.objects.get(name="Closed Co")
        self.assertTrue(entity.is_closed)

    def test_update_entity(self):
        entity = EntityFactory(name="Before")
        data = {"action": "save", "name": "After", "is_closed": "on"}
        response = self.client.post(
            reverse("settings-entity", args=[entity.id]), data=data
        )
        self.assertEqual(response.status_code, 200)
        entity.refresh_from_db()
        self.assertEqual(entity.name, "After")
        self.assertTrue(entity.is_closed)

    def test_delete_unused_entity(self):
        entity = EntityFactory()
        response = self.client.post(
            reverse("settings-entity", args=[entity.id]),
            data={"action": "delete"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Entity.objects.filter(pk=entity.id).exists())

    def test_delete_protected_entity_shows_message(self):
        entity = EntityFactory(name="Busy Entity")
        # Loan.entity is PROTECT, so the delete is blocked.
        LoanFactory(entity=entity)

        response = self.client.post(
            reverse("settings-entity", args=[entity.id]),
            data={"action": "delete"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Can&#x27;t delete")
        self.assertTrue(Entity.objects.filter(pk=entity.id).exists())

    def test_duplicate_name_shows_form_error(self):
        EntityFactory(name="Acme")
        data = {"action": "save", "name": "Acme", "is_closed": ""}
        response = self.client.post(reverse("settings-entities"), data=data)
        self.assertEqual(response.status_code, 200)
        # Only the original entity exists; the duplicate is rejected.
        self.assertEqual(Entity.objects.filter(name="Acme").count(), 1)
        self.assertContains(response, "already exists")
