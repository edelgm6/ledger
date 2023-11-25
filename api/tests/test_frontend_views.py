from datetime import date
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.contrib.auth.models import User
from api.models import TaxCharge, Transaction, Account
from api.statement import IncomeStatement

class TaxesViewTest(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username='testuser', password='12345')

        # Create account instances
        account1 = Account.objects.create(
            name='Account 1',
            type=Account.Type.ASSET,
            sub_type=Account.SubType.CASH
        )
        account2 = Account.objects.create(
            name='Account 2',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX
        )
        account3 = Account.objects.create(
            name='Account 3',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.LONG_TERM_DEBT
        )

        # Create the special account required by TaxCharge's save method
        state_tax_account = Account.objects.create(
            name='State Taxes Account',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
            special_type=Account.SpecialType.STATE_TAXES
        )
        fed_tax_account = Account.objects.create(
            name='Fed Taxes Account',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
            special_type=Account.SpecialType.FEDERAL_TAXES
        )
        property_tax_account = Account.objects.create(
            name='Prop Taxes Account',
            type=Account.Type.EXPENSE,
            sub_type=Account.SubType.TAX,
            special_type=Account.SpecialType.PROPERTY_TAXES
        )
        state_pay_account = Account.objects.create(
            name='State Taxes Pay Account',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.TAXES_PAYABLE,
            special_type=Account.SpecialType.STATE_TAXES_PAYABLE
        )
        fed_pay_account = Account.objects.create(
            name='Fed Taxes Pay Account',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.TAXES_PAYABLE,
            special_type=Account.SpecialType.FEDERAL_TAXES_PAYABLE
        )
        property_pay_account = Account.objects.create(
            name='Prop Taxes Pay Account',
            type=Account.Type.LIABILITY,
            sub_type=Account.SubType.TAXES_PAYABLE,
            special_type=Account.SpecialType.PROPERTY_TAXES_PAYABLE
        )

        # Create transactions
        transaction1 = Transaction.objects.create(
            date=date.today(),
            account=account1,
            amount=1000.00,
            description="Transaction 1",
            category="Category 1",
            type=Transaction.TransactionType.INCOME
        )
        transaction2 = Transaction.objects.create(
            date=date.today(),
            account=account2,
            amount=2000.00,
            description="Transaction 2",
            category="Category 2",
            type=Transaction.TransactionType.PURCHASE
        )
        transaction3 = Transaction.objects.create(
            date=date.today(),
            account=account3,
            amount=3000.00,
            description="Transaction 3",
            category="Category 3",
            type=Transaction.TransactionType.PAYMENT
        )

        # Create tax charges
        TaxCharge.objects.create(type=TaxCharge.Type.PROPERTY, transaction=transaction1, date=date.today(), amount=100.00)
        TaxCharge.objects.create(type=TaxCharge.Type.FEDERAL, transaction=transaction2, date=date.today(), amount=200.00)
        TaxCharge.objects.create(type=TaxCharge.Type.STATE, transaction=transaction3, date=date.today(), amount=300.00)

    def test_redirect_if_not_logged_in(self):
        response = self.client.get(reverse('taxes'))  # replace 'taxes' with the actual name of your view in urls.py
        self.assertRedirects(response, '/login/?next=/taxes/')  # adjust the redirect URL based on your login configuration

    def test_logged_in_uses_correct_template(self):
        self.client.login(username='testuser', password='12345')
        response = self.client.get(reverse('taxes'))

        # Check our user is logged in
        self.assertEqual(str(response.context['user']), 'testuser')
        # Check that we got a response "success"
        self.assertEqual(response.status_code, 200)

        # Check we used the correct template
        self.assertTemplateUsed(response, 'api/taxes.html')  # replace 'taxes.html' with your actual template

        # Check the content of the response
        self.assertIn(b'Taxes', response.content)

    def test_tax_charges_in_context(self):
        self.client.login(username='testuser', password='12345')
        response = self.client.get(reverse('taxes'))

        # Check the response context
        self.assertIn('tax_charges', response.context)
        self.assertIn('tax_charge_table', response.context)
        tax_charges_context = response.context['tax_charges']

        # Check that the context is not empty
        self.assertIsNotNone(tax_charges_context)

        # Check the number of tax charges in context matches the number created
        self.assertEqual(tax_charges_context.count(), 3)

        # Check if the tax charges in the context are the same as those created
        # Assuming you have a way to identify each uniquely (e.g., by a combination of attributes)
        created_tax_charges = TaxCharge.objects.all()
        for tax_charge in created_tax_charges:
            self.assertIn(tax_charge, tax_charges_context)
