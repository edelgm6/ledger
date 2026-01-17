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

    @patch('api.models.Document')
    @patch('api.models.get_textract_results')
    def test_extract_data(self, mock_get_textract_results, mock_document_class):
        """Test that _extract_data processes textract results correctly."""
        # Mock the textract response
        mock_get_textract_results.return_value = {'DocumentMetadata': {'Pages': 1}, 'Blocks': []}

        # Mock page
        mock_page = MagicMock()
        mock_page.id = 'page-1'

        # Mock the Document.open() to return a mock document with pages and key-value pairs
        mock_document = MagicMock()
        mock_document.pages = [mock_page]
        mock_document.tables = []

        # Mock key-value pair
        mock_kv = MagicMock()
        mock_kv.key = MagicMock()
        mock_kv.key.text = 'Company'
        mock_kv.value = MagicMock()
        mock_kv.value.text = 'Test Corp'
        mock_kv.page_id = 'page-1'  # Must match a page id
        mock_document.key_values = [mock_kv]

        mock_document_class.open.return_value = mock_document

        prefill = Prefill.objects.create(name='Opendoor')

        s3file = S3File.objects.create(
            prefill=prefill,
            url='https://google.com',
            user_filename='block pay.pdf',
            s3_filename='block pay.pdf',
            textract_job_id='mock-job-id'
        )
        DocSearch.objects.create(
            prefill=prefill,
            keyword='Company',
            selection='Company'
        )

        # Call the private method
        data = s3file._extract_data()

        # Verify data was extracted
        self.assertIsInstance(data, dict)
        self.assertIn('page-1', data)
        self.assertEqual(data['page-1'].get('Company'), 'Test Corp')
        # Verify the mock was called
        mock_document_class.open.assert_called_once()


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
