from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from api.models import Account, Transaction, JournalEntry, JournalEntryItem
from api.views import JournalEntryView

class JournalEntryViewTest(TestCase):
    def setUp(self):
        self.ENDPOINT = '/journal-entries/'
        self.VIEW = JournalEntryView

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
            'sub_type': 'purchases',
            'mock': 'true'
        }

        factory = APIRequestFactory()
        request = factory.get(self.ENDPOINT, payload, format='json')
        force_authenticate(request, user=user)
        response = self.VIEW.as_view()(request)
        self.assertEqual(response.status_code, 200)
        print(response.data)