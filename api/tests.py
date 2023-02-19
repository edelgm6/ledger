from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from api.models import Account, Transaction
from api.views import AccountView, UploadTransactionsView, TransactionView

class AccountViewTest(TestCase):

    def setUp(self):
        self.ENDPOINT = '/accounts/'
        self.VIEW = AccountView

    def test_must_be_authenticated(self):
        factory = APIRequestFactory()
        request = factory.get(self.ENDPOINT)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 401)

    def test_can_view_accounts(self):
        user = User.objects.create(username='admin')
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='credit_card'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchase'
        )
        factory = APIRequestFactory()
        request = factory.get(self.ENDPOINT)
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('1200-Chase' in response.data[0].values())
        self.assertTrue('5000-Groceries' in response.data[1].values())

class TransactionViewTest(TestCase):

    def setUp(self):
        self.ENDPOINT = '/transactions/'
        self.VIEW = TransactionView

    def test_must_be_authenticated(self):
        factory = APIRequestFactory()
        request = factory.get(self.ENDPOINT)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 401)

class UploadTransactionsViewTest(TestCase):

    def setUp(self):
        self.ENDPOINT = '/upload-transactions/'
        self.VIEW = UploadTransactionsView

    def test_must_be_authenticated(self):
        factory = APIRequestFactory()
        request = factory.get(self.ENDPOINT)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 401)

    def test_upload_transactions(self):
        user = User.objects.create(username='admin')

        account = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='credit_card'
        )

        factory = APIRequestFactory()
        payload = {
            'account': account.name,
            'transactions': [{
                'date': '2023-01-01',
                'amount': -11.50,
                'category': 'transfer',
                'description': 'uber ride',
            }]
        }
        request = factory.post(self.ENDPOINT, payload, format='json')
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 201)
        transaction = Transaction.objects.get(category='transfer')
        self.assertEqual(transaction.account, account)
        self.assertEqual(transaction.description, 'uber ride')
