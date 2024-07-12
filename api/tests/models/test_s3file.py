from django.test import TestCase
from api.models import S3File

class S3FileTests(TestCase):

    def test_create_reconciliation(self):
        s3file = S3File.objects.create(
            url='https://google.com',
            user_filename='block pay.pdf',
            s3_filename='03378dc8-1957-4ebe-b15e-f43893a5cf45.pdf'
        )
        response = s3file.process_document_with_textract()
        s3file.refresh_from_db()
        self.assertEqual(response, s3file.textract_job_id)