from django.test import TestCase
from decimal import Decimal
from unittest.mock import patch, MagicMock
from api.models import S3File, DocSearch, Account, Prefill, Paystub, PaystubValue


class S3FileTests(TestCase):

    @patch('api.models.create_textract_job')
    def test_start_textract_job(self, mock_create_textract_job):
        mock_create_textract_job.return_value = 'mock-job-id-12345'

        prefill = Prefill.objects.create(name='Opendoor')
        s3file = S3File.objects.create(
            prefill=prefill,
            url='https://google.com',
            user_filename='block pay.pdf',
            s3_filename='block pay.pdf'
        )
        response = s3file.create_textract_job()
        s3file.refresh_from_db()
        self.assertEqual(response, 'mock-job-id-12345')
        self.assertEqual(s3file.textract_job_id, 'mock-job-id-12345')

    @patch('api.aws_services.get_boto3_client')
    def test_get_textract_response(self, mock_get_client):
        """Test that get_textract_results properly handles pagination."""
        from api.aws_services import get_textract_results

        mock_textract_client = MagicMock()
        mock_textract_client.get_document_analysis.side_effect = [
            {"DocumentMetadata": {"Pages": 1}, "Blocks": [{"Id": "1"}], "NextToken": "next"},
            {"DocumentMetadata": {"Pages": 1}, "Blocks": [{"Id": "2"}]},
        ]
        mock_get_client.return_value = mock_textract_client

        response = get_textract_results(job_id='mock-job-id')
        self.assertEqual(response['DocumentMetadata']['Pages'], 1)
        self.assertEqual(len(response['Blocks']), 2)


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
        self.assertFalse(s3file.textract_job_id)  # Empty string or None
