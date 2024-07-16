from django.test import TestCase
from decimal import Decimal
from api.models import S3File, DocSearch, Account, Prefill, Paystub, PaystubValue

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

# class DocSearch(models.Model):
#     keyword = models.CharField(max_length=200, null=True, blank=True)
#     table_name = models.CharField(max_length=200, null=True, blank=True)
#     row = models.CharField(max_length=200, null=True, blank=True)
#     column = models.CharField(max_length=200, null=True, blank=True)
#     account = models.ForeignKey('Account', null=True, blank=True, on_delete=models.SET_NULL)
    
#     STRING_CHOICES = [
#         ('Company', 'Company'),
#         ('Begin Period', 'Begin Period'),
#         ('End Period', 'End Period'),
#     ]
#     selection = models.CharField(max_length=20, choices=STRING_CHOICES, null=True, blank=True)


    # name = models.CharField(max_length=200, unique=True)
    # type = models.CharField(max_length=9, choices=Type.choices)
    # sub_type = models.CharField(max_length=30, choices=SubType.choices)
    # csv_profile = models.ForeignKey(
    #     'CSVProfile',
    #     related_name='accounts',
    #     on_delete=models.PROTECT,
    #     null=True,
    #     blank=True
    # )
    # special_type = models.CharField(
    #     max_length=30,
    #     choices=SpecialType.choices,
    #     null=True,
    #     blank=True,
    #     unique=True
    # )
    # is_closed = models.BooleanField(default=False)

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

        responses = s3file.get_textract_results()
        combined_response = s3file.combine_responses(responses)
        data = s3file.extract_data(combined_response)
        print(data)

        self.assertEqual(data['66d467aa-4c6c-4961-bbfb-60bd27607814']['Company'], 'Opendoor Labs Inc.')
        self.assertEqual(data['66d467aa-4c6c-4961-bbfb-60bd27607814'][salary_account], Decimal('8801.47'))
        self.assertEqual(data['66d467aa-4c6c-4961-bbfb-60bd27607814'][tax_account], Decimal('1447.36'))

        s3file.create_paystubs_from_textract_data(data)

        paystub = Paystub.objects.get(pk=1)
        paystub_values = PaystubValue.objects.filter(paystub=paystub)
        self.assertEqual(paystub_values.count(), 2)
