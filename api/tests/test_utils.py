from decimal import Decimal, InvalidOperation

from django.test import SimpleTestCase

from api.utils import friendly_error_message, parse_currency, short_error_label


class ParseCurrencyTest(SimpleTestCase):
    def test_parses_plain_and_signed_numbers(self):
        self.assertEqual(parse_currency("805.36"), Decimal("805.36"))
        self.assertEqual(parse_currency("-805.36"), Decimal("-805.36"))

    def test_strips_thousands_separators_and_dollar_signs(self):
        self.assertEqual(parse_currency("$1,234.56"), Decimal("1234.56"))
        self.assertEqual(parse_currency("-1,000"), Decimal("-1000"))

    def test_returns_decimal_type(self):
        self.assertIsInstance(parse_currency("10"), Decimal)

    def test_raises_on_garbage(self):
        with self.assertRaises(InvalidOperation):
            parse_currency("not a number")


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
