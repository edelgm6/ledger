from django.test import TestCase
from api.models import S3File

class S3FileTests(TestCase):

    def test_process_with_textract(self):
        s3file = S3File.objects.create(
            url='https://google.com',
            user_filename='block pay.pdf',
            s3_filename='block pay.pdf'
        )
        response = s3file.process_document_with_textract()
        s3file.refresh_from_db()
        self.assertEqual(response, s3file.textract_job_id)

    def test_get_textract_response(self):
        s3file = S3File.objects.create(
            url='https://google.com',
            user_filename='block pay.pdf',
            s3_filename='block pay.pdf',
            textract_job_id='37244276228a8ce27b25063cb6da1a02fb6b2166a4c6a960c286b20cc8a669a9'
        )
        responses = s3file.get_textract_results()
        combined_response = s3file.combine_responses(responses)
        print(combined_response)
        self.assertEqual(combined_response['DocumentMetadata']['Pages'], 1)

    def test_extract_data(self):
        s3file = S3File.objects.create(
            url='https://google.com',
            user_filename='block pay.pdf',
            s3_filename='block pay.pdf',
            textract_job_id='37244276228a8ce27b25063cb6da1a02fb6b2166a4c6a960c286b20cc8a669a9'
        )
        responses = s3file.get_textract_results()
        combined_response = s3file.combine_responses(responses)
        data = s3file.extract_data(combined_response)

        self.assertEqual(data['66d467aa-4c6c-4961-bbfb-60bd27607814']['gross'], '8,801.47')