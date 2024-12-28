import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import UUID

from api.aws_services import (
    clean_and_convert_string_to_decimal,
    clean_string,
    combine_responses,
    create_textract_job,
    generate_unique_filename,
    get_boto3_client,
    get_textract_results,
    upload_file_to_s3,
)


class AWSTests(unittest.TestCase):
    @patch("api.aws_services.boto3.client")
    def test_get_boto3_client(self, mock_boto3):
        mock_boto3.return_value = "mock_client"
        client = get_boto3_client(service="s3")

        self.assertEqual(client, "mock_client")
        mock_boto3.assert_called_once_with(
            "s3",
            aws_access_key_id="fake_access_key",
            aws_secret_access_key="fake_secret_key",
            region_name="fake_region",
        )

    def test_generate_unique_filename(self):
        class MockFile:
            name = "example.pdf"

        file = MockFile()
        unique_filename = generate_unique_filename(file)

        self.assertTrue(unique_filename.endswith(".pdf"))
        self.assertTrue(UUID(unique_filename.split(".")[0]))  # Ensure UUID is valid

    @patch("your_module.get_boto3_client")
    def test_upload_file_to_s3_success(self, mock_get_client):
        mock_s3_client = MagicMock()
        mock_get_client.return_value = mock_s3_client

        class MockFile:
            content_type = "application/pdf"
            name = "example.pdf"

        file = MockFile()
        result = upload_file_to_s3(file)

        self.assertIsInstance(result, str)  # Should return the unique filename
        mock_s3_client.upload_fileobj.assert_called_once()

    @patch("your_module.get_boto3_client")
    def test_upload_file_to_s3_failure(self, mock_get_client):
        mock_s3_client = MagicMock()
        mock_s3_client.upload_fileobj.side_effect = Exception("Upload failed")
        mock_get_client.return_value = mock_s3_client

        class MockFile:
            content_type = "application/pdf"
            name = "example.pdf"

        file = MockFile()
        result = upload_file_to_s3(file)

        self.assertEqual(result["error"], "Upload failed")
        self.assertEqual(result["message"], "Upload failed")

    @patch("your_module.get_boto3_client")
    def test_create_textract_job(self, mock_get_client):
        mock_textract_client = MagicMock()
        mock_textract_client.start_document_analysis.return_value = {"JobId": "12345"}
        mock_get_client.return_value = mock_textract_client

        filename = "example.pdf"
        job_id = create_textract_job(filename)

        self.assertEqual(job_id, "12345")
        mock_textract_client.start_document_analysis.assert_called_once_with(
            DocumentLocation={"S3Object": {"Bucket": "fake_bucket", "Name": filename}},
            FeatureTypes=["FORMS", "TABLES"],
        )

    @patch("your_module.get_boto3_client")
    def test_get_textract_results(self, mock_get_client):
        mock_textract_client = MagicMock()
        mock_textract_client.get_document_analysis.side_effect = [
            {"Blocks": [{"Id": "1"}], "NextToken": "next"},
            {"Blocks": [{"Id": "2"}], "NextToken": None},
        ]
        mock_get_client.return_value = mock_textract_client

        job_id = "12345"
        results = get_textract_results(job_id)

        self.assertEqual(len(results["Blocks"]), 2)  # Combine two responses
        self.assertEqual(results["Blocks"][0]["Id"], "1")
        self.assertEqual(results["Blocks"][1]["Id"], "2")

    def test_combine_responses(self):
        responses = [
            {"DocumentMetadata": {"Pages": 1}, "Blocks": [{"Id": "1"}]},
            {"DocumentMetadata": {"Pages": 2}, "Blocks": [{"Id": "2"}]},
        ]
        combined = combine_responses(responses)

        self.assertEqual(combined["DocumentMetadata"]["Pages"], 2)
        self.assertEqual(len(combined["Blocks"]), 2)

    def test_clean_string(self):
        self.assertEqual(clean_string("  Hello, World!  "), "Hello World!")
        self.assertEqual(clean_string("Multiple    spaces"), "Multiple spaces")
        self.assertIsNone(clean_string(None))

    def test_clean_and_convert_string_to_decimal(self):
        self.assertEqual(
            clean_and_convert_string_to_decimal("$1,234.56"), Decimal("1234.56")
        )
        self.assertEqual(clean_and_convert_string_to_decimal(None), Decimal("0.00"))
        self.assertEqual(clean_and_convert_string_to_decimal("abc"), Decimal("0.00"))
