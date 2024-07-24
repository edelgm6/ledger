from django.test import TestCase
from decimal import Decimal
from api.models import S3File, DocSearch, Account, Prefill, Paystub, PaystubValue
from api.aws_services import create_textract_job, get_textract_results

class S3FileTests(TestCase):

    def test_start_textract_job(self):
        prefill = Prefill.objects.create(name='Opendoor')
        s3file = S3File.objects.create(
            prefill=prefill,
            url='https://google.com',
            user_filename='block pay.pdf',
            s3_filename='block pay.pdf'
        )
        response = s3file.create_textract_job()
        s3file.refresh_from_db()
        self.assertEqual(response, s3file.textract_job_id)

    def test_get_textract_response(self):
        response = get_textract_results(job_id='37244276228a8ce27b25063cb6da1a02fb6b2166a4c6a960c286b20cc8a669a9')
        self.assertEqual(response['DocumentMetadata']['Pages'], 1)

    def test_extract_data(self):
        prefill = Prefill.objects.create(name='Opendoor')
        
        s3file = S3File.objects.create(
            prefill=prefill,
            url='https://google.com',
            user_filename='block pay.pdf',
            s3_filename='block pay.pdf',
            textract_job_id='37244276228a8ce27b25063cb6da1a02fb6b2166a4c6a960c286b20cc8a669a9'
        )
        DocSearch.objects.create(
            prefill=prefill,
            keyword='Company',
            selection='Company'
        )
        DocSearch.objects.create(
            prefill=prefill,
            keyword='Pay Period End',
            selection='Begin Period'
        )
        DocSearch.objects.create(
            prefill=prefill,
            keyword='Pay Period Begin',
            selection='End Period'
        )
        salary_account = Account.objects.create(
            name='1000-Salary',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY
        )
        DocSearch.objects.create(
            prefill=prefill,
            row='Current',
            column='Gross Pay',
            account=salary_account
        )
        tax_account = Account.objects.create(
            name='2000-Taxes',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.TAXES_PAYABLE
        )
        DocSearch.objects.create(
            prefill=prefill,
            row='Federal Withholding',
            column='Amount',
            table_name='Employee Taxes',
            account=tax_account
        )

        data = s3file.extract_data()

        self.assertEqual(data['66d467aa-4c6c-4961-bbfb-60bd27607814']['Company'], 'Opendoor Labs Inc.')
        self.assertEqual(data['66d467aa-4c6c-4961-bbfb-60bd27607814'][salary_account], Decimal('8801.47'))
        self.assertEqual(data['66d467aa-4c6c-4961-bbfb-60bd27607814'][tax_account], Decimal('1447.36'))

        s3file.create_paystubs_from_textract_data()

        paystub = Paystub.objects.get(pk=1)
        paystub_values = PaystubValue.objects.filter(paystub=paystub)
        self.assertEqual(paystub_values.count(), 2)
