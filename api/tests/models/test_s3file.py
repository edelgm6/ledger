from django.test import TestCase

from api.models import S3File, Prefill


class S3FileCreationTests(TestCase):
    """Tests for S3File model creation without AWS calls."""

    def test_create_s3file(self):
        prefill = Prefill.objects.create(name='Test Prefill')
        s3file = S3File.objects.create(
            prefill=prefill,
            url='https://example.com/test.pdf',
            user_filename='test.pdf',
            s3_filename='unique-test.pdf'
        )
        self.assertEqual(s3file.user_filename, 'test.pdf')
        self.assertEqual(s3file.s3_filename, 'unique-test.pdf')


class S3FileShortErrorTests(TestCase):
    """Tests for the S3File.short_error display property."""

    def setUp(self):
        self.prefill = Prefill.objects.create(name='Test Prefill')

    def _s3file(self, error_message):
        return S3File(
            prefill=self.prefill,
            url='https://example.com/test.pdf',
            user_filename='test.pdf',
            s3_filename='unique-test.pdf',
            error_message=error_message,
        )

    def test_maps_503_to_server_busy(self):
        msg = "503 UNAVAILABLE. {'error': {'code': 503, 'message': 'high demand'}}"
        self.assertEqual(self._s3file(msg).short_error, 'server busy (503)')

    def test_maps_429_to_rate_limited(self):
        self.assertEqual(self._s3file('429 RESOURCE_EXHAUSTED').short_error, 'rate limited (429)')

    def test_defaults_to_processing_error(self):
        self.assertEqual(self._s3file('KeyError: Company').short_error, 'processing error')
