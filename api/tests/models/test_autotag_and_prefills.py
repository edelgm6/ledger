from django.test import TestCase
from api.tests.testing_factories import AutoTagFactory, PrefillFactory, AccountFactory

class AutoTagModelTest(TestCase):
    def setUp(self):
        self.account = AccountFactory()
        self.prefill = PrefillFactory()
        self.auto_tag = AutoTagFactory(search_string="test", account=self.account, prefill=self.prefill)

    def test_auto_tag_creation(self):
        """Test the creation of an AutoTag instance."""
        self.assertIsNotNone(self.auto_tag.pk, "Should create an AutoTag instance")

    def test_auto_tag_str_representation(self):
        """Test the string representation of the AutoTag model."""
        expected_representation = f'"{self.auto_tag.search_string}": {self.auto_tag.account}'
        self.assertEqual(str(self.auto_tag), expected_representation, "String representation should be correct")

class PrefillModelTest(TestCase):
    def setUp(self):
        self.prefill = PrefillFactory(name="Test Prefill")

    def test_prefill_creation(self):
        """Test the creation of a Prefill instance."""
        self.assertIsNotNone(self.prefill.pk, "Should create a Prefill instance")

    def test_prefill_str_representation(self):
        """Test the string representation of the Prefill model."""
        self.assertEqual(str(self.prefill), self.prefill.name, "String representation should be the name of the Prefill")

