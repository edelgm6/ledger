import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from api.aws_services import (
    generate_unique_filename,
    get_boto3_client,
    upload_file_to_s3,
)


class AWSTests(unittest.TestCase):
    @patch("api.aws_services.settings")
    @patch("api.aws_services.boto3.client")
    def test_get_boto3_client(self, mock_boto3, mock_settings):
        # Mock the settings values
        mock_settings.AWS_ACCESS_KEY_ID = "fake_access_key"
        mock_settings.AWS_SECRET_ACCESS_KEY = "fake_secret_key"
        mock_settings.AWS_REGION_NAME = "fake_region"
        mock_settings.AWS_VERIFY = True

        mock_boto3.return_value = "mock_client"
        client = get_boto3_client(service="s3")

        self.assertEqual(client, "mock_client")
        mock_boto3.assert_called_once_with(
            "s3",
            aws_access_key_id="fake_access_key",
            aws_secret_access_key="fake_secret_key",
            region_name="fake_region",
            verify=True,
        )

    def test_generate_unique_filename(self):
        class MockFile:
            name = "example.pdf"

        file = MockFile()
        unique_filename = generate_unique_filename(file)

        self.assertTrue(unique_filename.endswith(".pdf"))
        self.assertTrue(UUID(unique_filename.split(".")[0]))  # Ensure UUID is valid

    @patch("api.aws_services.get_boto3_client")
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

    @patch("api.aws_services.get_boto3_client")
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
