import datetime
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIRequestFactory, force_authenticate
from api.models import Account, Transaction, JournalEntry, JournalEntryItem, CSVProfile, AutoTag, Reconciliation
from api.views import AccountView, UploadTransactionsView, TransactionView, JournalEntryView, TransactionTypeView, CSVProfileView, AccountBalanceView, ReconciliationView, GenerateReconciliationsView, PlugReconciliationView

class PlugReconciliationViewTest(TestCase):
    def setUp(self):
        self.ENDPOINT = '/reconciliations/'
        self.VIEW = PlugReconciliationView

    def test_returns_200(self):
        user = User.objects.create(username='admin')
        factory = APIRequestFactory()

        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )
        gain_loss_account = Account.objects.create(
            name='4050-Investment Gains or Losses',
            type='expense',
            sub_type='purchases',
            special_type=Account.SpecialType.UNREALIZED_GAINS_AND_LOSSES
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=groceries
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-01',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=groceries,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        reconciliation = Reconciliation.objects.create(
            account=chase,
            date='2023-01-31',
            amount=500
        )

        request = factory.put(self.ENDPOINT + str(reconciliation.pk) + '/plug/')
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request,pk=reconciliation.pk)
        self.assertEqual(response.status_code, 200)
        plug_items = JournalEntryItem.objects.filter(amount=400)
        self.assertEqual(plug_items.count(),2)

class ReconciliationsCreateViewTest(TestCase):
    def setUp(self):
        self.ENDPOINT = '/reconciliations/generate/'
        self.VIEW = GenerateReconciliationsView
        gains_losses_account = Account.objects.create(
            name='8000-Gains',
            type=Account.Type.EQUITY,
            sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS
        )
        income = Account.objects.create(
            name='8000-Income',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=income
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=income,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=gains_losses_account,
            journal_entry=journal_entry
        )

    def test_bad_date_returns_404(self):
        user = User.objects.create(username='admin')
        factory = APIRequestFactory()

        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=groceries
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-01',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=groceries,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        request = factory.post(self.ENDPOINT,{'date': '2023-01-15'})
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 400)

    def test_returns_200(self):
        user = User.objects.create(username='admin')
        factory = APIRequestFactory()

        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=groceries
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-01',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=groceries,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        request = factory.post(self.ENDPOINT,{'date': '2023-01-31'})
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 200)

class ReconciliationsViewTest(TestCase):
    def setUp(self):
        self.ENDPOINT = '/reconciliations/'
        self.VIEW = ReconciliationView
        gains_losses_account = Account.objects.create(
            name='8000-Gains',
            type=Account.Type.EQUITY,
            sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS
        )

        income = Account.objects.create(
            name='8000-Income',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=income
        )
        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=income,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=gains_losses_account,
            journal_entry=journal_entry
        )

    def test_put_updates_objects(self):
        user = User.objects.create(username='admin')
        factory = APIRequestFactory()

        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=groceries
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-01',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=groceries,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        reconciliation = Reconciliation.objects.create(
            date='2023-01-31',
            account=chase
        )

        payload = [
            {
                'id': reconciliation.id,
                'amount': 500
            }

        ]

        request = factory.put(self.ENDPOINT,payload, format='json')
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 200)
        reconciliation = Reconciliation.objects.get(account=chase)
        self.assertEqual(reconciliation.amount, 500)

    def test_returns_200(self):
        user = User.objects.create(username='admin')
        factory = APIRequestFactory()

        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=groceries
        )

        journal_entry = JournalEntry.objects.create(date='2023-01-01',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=groceries,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        reconciliation = Reconciliation.objects.create(
            date='2023-01-31',
            account=chase
        )

        request = factory.get(self.ENDPOINT,{'date': ['2023-01-31']})
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['current_balance'], 100)

class AccountBalanceViewTest(TestCase):
    def setUp(self):
        self.ENDPOINT = '/account-balances/'
        self.VIEW = AccountBalanceView
        gains_losses_account = Account.objects.create(
            name='8000-Gains',
            type=Account.Type.EQUITY,
            sub_type=Account.SubType.UNREALIZED_INVESTMENT_GAINS
        )
        income = Account.objects.create(
            name='8000-Income',
            type=Account.Type.INCOME,
            sub_type=Account.SubType.SALARY
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100.,
            account=income
        )
        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=income,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=gains_losses_account,
            journal_entry=journal_entry
        )

    def test_returns_balance(self):
        user = User.objects.create(username='admin')
        factory = APIRequestFactory()

        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )

        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=groceries
        )
        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=groceries,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        payload = {
            'start_date': '2022-12-31',
            'end_date': '2023-01-31'
        }

        request = factory.get(self.ENDPOINT, payload)
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['balance_sheet']['balances'][0]['account'], chase.name)
        self.assertEqual(len(response.data), 3)

    def test_returns_200(self):
        user = User.objects.create(username='admin')
        factory = APIRequestFactory()

        payload = {
            'start_date': '2022-12-31',
            'end_date': '2023-01-31'
        }

        request = factory.get(self.ENDPOINT, payload)
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 200)

class CSVProfileViewTest(TestCase):
    def setUp(self):
        self.ENDPOINT = '/csv-profiles/'
        self.VIEW = CSVProfileView

    def test_returns_csv_profiles(self):
        user = User.objects.create(username='admin')
        profile = CSVProfile.objects.create(
            name='name',
            date='date',
            amount='amount',
            description='description',
            category='category'
        )
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt',
            csv_profile=profile
        )

        factory = APIRequestFactory()
        request = factory.get(self.ENDPOINT)
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CSVProfile.objects.get(pk=1), profile)

class TransactionTypeViewTest(TestCase):
    def setUp(self):
        self.ENDPOINT = '/transaction-types/'
        self.VIEW = TransactionTypeView

    def test_returns_transaction_types(self):
        user = User.objects.create(username='admin')
        factory = APIRequestFactory()
        request = factory.get(self.ENDPOINT)
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('id' in response.data[0].keys())

class JournalEntryViewTest(TestCase):
    def setUp(self):
        self.ENDPOINT = '/journal-entries/'
        self.VIEW = JournalEntryView

    def test_must_be_authenticated(self):
        factory = APIRequestFactory()
        request = factory.get(self.ENDPOINT)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 401)

    def test_get_journal_entries(self):
        user = User.objects.create(username='admin')
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100,
            account=groceries
        )
        journal_entry = JournalEntry.objects.create(date='2023-01-28',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100,
            account=groceries,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100,
            account=chase,
            journal_entry=journal_entry
        )

        payload = {
            'sub_type': 'purchases'
        }

        factory = APIRequestFactory()
        request = factory.get(self.ENDPOINT, payload, format='json')
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_fails_if_debit_credit_imbalance(self):
        user = User.objects.create(username='admin')
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )

        payload = {
            'date': '2023-01-01',
            'journal_entry_items': [
                {
                    'type': 'debit',
                    'amount': 100,
                    'account': '1200-Chase'
                },
                {
                    'type': 'credit',
                    'amount': 50,
                    'account': '5000-Groceries'
                }
            ]
        }
        factory = APIRequestFactory()
        request = factory.post(self.ENDPOINT, payload, format='json')
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 400)

    def test_create_journal_entry_with_nulls(self):
        user = User.objects.create(username='admin')
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )
        transaction = Transaction.objects.create(
            date='2023-01-28',
            amount=100.23,
            account=groceries
        )

        payload = {
            'date': '2023-01-01',
            'transaction': transaction.pk,
            'transaction_type': None,
            'journal_entry_items': [
                {
                    'type': 'debit',
                    'amount': 100.23,
                    'account': '1200-Chase'
                },
                {
                    'type': 'credit',
                    'amount': 100.23,
                    'account': '5000-Groceries'
                }
            ]
        }
        factory = APIRequestFactory()
        request = factory.post(self.ENDPOINT, payload, format='json')
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 201)
        journal_entry = JournalEntry.objects.get(pk=1)
        journal_entry_items = JournalEntryItem.objects.all()
        self.assertEqual(journal_entry.date, datetime.date(2023, 1, 1))
        self.assertEqual(journal_entry_items.count(), 2)

    def test_create_journal_entry(self):
        user = User.objects.create(username='admin')
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )
        transaction = Transaction.objects.create(
            date='2023-01-01',
            account=chase,
            amount=-100.23,
            description='test whatever',
            category='whatever',
            type=Transaction.TransactionType.INCOME
        )

        payload = {
            'date': '2023-01-01',
            'transaction': transaction.pk,
            'transaction_type': 'payment',
            'journal_entry_items': [
                {
                    'type': 'debit',
                    'amount': 100.23,
                    'account': '1200-Chase'
                },
                {
                    'type': 'credit',
                    'amount': 100.23,
                    'account': '5000-Groceries'
                }
            ]
        }
        factory = APIRequestFactory()
        request = factory.post(self.ENDPOINT, payload, format='json')
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 201)
        journal_entry = JournalEntry.objects.get(pk=1)
        journal_entry_items = JournalEntryItem.objects.all()
        self.assertEqual(journal_entry.date, datetime.date(2023, 1, 1))
        self.assertEqual(journal_entry.transaction, transaction)
        self.assertEqual(journal_entry_items.count(), 2)
        transaction = Transaction.objects.get(pk=1)
        self.assertEqual(transaction.type, 'payment')

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
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
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

    def test_create_transaction(self):
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )

        user = User.objects.create(username='admin')
        factory = APIRequestFactory()
        payload = {
            'date': '2023-02-24',
            'amount': 120.11,
            'description': 'test description',
            'category': 'deposit',
            'type': Transaction.TransactionType.INCOME,
            'account': chase.name
        }

        request = factory.post(self.ENDPOINT, payload)
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 201)
        self.assertTrue('test description' in response.data.values())
        transaction = Transaction.objects.get(pk=1)

    def test_modify_transaction(self):
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )

        transaction = Transaction.objects.create(
            date='2023-01-01',
            account=chase,
            amount=-100.23,
            description='test whatever',
            category='whatever',
            type=Transaction.TransactionType.PAYMENT
        )

        user = User.objects.create(username='admin')
        factory = APIRequestFactory()
        payload = {
            'is_closed': True,
            'description': 'changed description'
        }

        request = factory.put('transactions/1/', payload)
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request,pk=1)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('test whatever' not in response.data.values())
        self.assertTrue('changed description' in response.data.values())
        transaction = Transaction.objects.get(pk=1)
        self.assertTrue(transaction.is_closed)


    def test_get_exclude_exclude_params(self):
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )
        groceries = Account.objects.create(
            name='5000-Groceries',
            type='expense',
            sub_type='purchases'
        )

        transaction = Transaction.objects.create(
            date='2023-01-01',
            account=chase,
            amount=-100.23,
            description='test whatever',
            category='whatever',
            type=Transaction.TransactionType.PAYMENT
        )

        transaction = Transaction.objects.create(
            date='2023-01-01',
            account=chase,
            amount=-10.23,
            description='test exclude',
            category='whatever',
            type=Transaction.TransactionType.PURCHASE,
            linked_transaction=transaction
        )
        journal_entry = JournalEntry.objects.create(date='2023-01-01',transaction=transaction)
        journal_entry_debit = JournalEntryItem.objects.create(
            type='debit',
            amount=100.23,
            account=groceries,
            journal_entry=journal_entry
        )
        journal_entry_credit = JournalEntryItem.objects.create(
            type='credit',
            amount=100.23,
            account=chase,
            journal_entry=journal_entry
        )

        user = User.objects.create(username='admin')
        factory = APIRequestFactory()
        payload = {
            'exclude_type': ['payment','transfer'],
            'is_closed': False,
            'has_linked_transaction': True,
            'journal_entry_item_account_sub_type': 'short_term_debt'
        }

        request = factory.get(self.ENDPOINT, payload)
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('test whatever' not in response.data[0].values())
        self.assertTrue('test exclude' in response.data[0].values())

    def test_get_include_exclude_params(self):
        chase = Account.objects.create(
            name='1200-Chase',
            type='liability',
            sub_type='short_term_debt'
        )

        transaction = Transaction.objects.create(
            date='2023-01-01',
            account=chase,
            amount=-100.23,
            description='test whatever',
            category='whatever',
            type=Transaction.TransactionType.PAYMENT
        )

        transaction = Transaction.objects.create(
            date='2023-01-01',
            account=chase,
            amount=-10.23,
            description='test exclude',
            category='whatever',
            type=Transaction.TransactionType.PURCHASE
        )

        user = User.objects.create(username='admin')
        factory = APIRequestFactory()
        payload = {
            'include_type': ['payment','transfer'],
            'is_closed': False,
            'account': chase.name,
            'amount': 100.23
        }

        request = factory.get(self.ENDPOINT, payload)
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue('test whatever' in response.data[0].values())
        self.assertTrue('test exclude' not in response.data[0].values())


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
            sub_type='short_term_debt'
        )
        auto_tag = AutoTag.objects.create(
            search_string='uber',
            account=account,
            transaction_type='payment'
        )

        auto_tag_no_account = AutoTag.objects.create(
            search_string='dividend',
            transaction_type='transfer'
        )

        factory = APIRequestFactory()
        payload = [
            {
                'account': account.name,
                'date': '2023-01-01',
                'amount': -11.50,
                'category': 'transfer',
                'description': 'uber ride'
            },
            {
                'account': account.name,
                'date': '2023-01-01',
                'amount': -20.50,
                'description': 'dividend'
            }
        ]
        request = factory.post(self.ENDPOINT, payload, format='json')
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 201)
        transaction = Transaction.objects.get(category='transfer')
        self.assertEqual(transaction.account, account)
        self.assertEqual(transaction.description, 'uber ride')
        self.assertEqual(transaction.suggested_account, account)
        transaction = Transaction.objects.get(description='dividend')
