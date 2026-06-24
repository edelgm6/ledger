from django.test import SimpleTestCase

from api.utils import friendly_error_message, short_error_label


class ErrorLabelTest(SimpleTestCase):
    def test_short_error_label_classifies(self):
        self.assertEqual(short_error_label("503 UNAVAILABLE"), "server busy (503)")
        self.assertEqual(
            short_error_label("429 RESOURCE_EXHAUSTED"), "rate limited (429)"
        )
        self.assertEqual(short_error_label("KeyError: 'x'"), "processing error")
        self.assertEqual(short_error_label(""), "")

    def test_friendly_error_message_steers_toward_retry(self):
        self.assertIn("overloaded", friendly_error_message("503 UNAVAILABLE"))
        self.assertIn("rate limited", friendly_error_message("429 RESOURCE_EXHAUSTED"))
        # Generic (and empty) errors offer both retry and rephrase.
        generic = friendly_error_message("KeyError: 'x'")
        self.assertIn("retry", generic)
        self.assertIn("rephrase", generic)
        self.assertIn("retry", friendly_error_message(""))
