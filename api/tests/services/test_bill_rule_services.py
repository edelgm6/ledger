from django.test import TestCase

from api.models import Account, Transaction, UtilityBillRule
from api.services.bill_rule_services import (
    delete_bill_rule,
    get_bill_rule_form_options,
    get_bill_rules,
    save_bill_rule,
)
from api.tests.testing_factories import AccountFactory, EntityFactory


def cleaned(**kwargs):
    defaults = {
        "from_address": "billing@x.com",
        "subject": "Your bill",
        "account_number": "123",
        "address_hint": "",
        "transaction_description_match": "DOM",
        "account": AccountFactory(type=Account.Type.EXPENSE),
        "entity": None,
        "transaction_type": Transaction.TransactionType.PURCHASE,
    }
    defaults.update(kwargs)
    return defaults


class SaveBillRuleTest(TestCase):
    def test_create(self):
        result = save_bill_rule(cleaned())
        self.assertTrue(result.success)
        self.assertEqual(UtilityBillRule.objects.count(), 1)
        self.assertEqual(result.rule.account_number, "123")

    def test_update_in_place(self):
        rule = save_bill_rule(cleaned()).rule
        result = save_bill_rule(cleaned(account_number="999"), instance=rule)
        self.assertTrue(result.success)
        rule.refresh_from_db()
        self.assertEqual(rule.account_number, "999")
        self.assertEqual(UtilityBillRule.objects.count(), 1)


class DeleteBillRuleTest(TestCase):
    def test_delete(self):
        rule = save_bill_rule(cleaned()).rule
        result = delete_bill_rule(rule.id)
        self.assertTrue(result.success)
        self.assertFalse(UtilityBillRule.objects.filter(pk=rule.id).exists())

    def test_delete_missing(self):
        result = delete_bill_rule(99999)
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Rule not found.")


class FormOptionsTest(TestCase):
    def test_excludes_closed_accounts(self):
        AccountFactory(name="Open Acct", is_closed=False)
        AccountFactory(name="Closed Acct", is_closed=True)
        EntityFactory(name="Some Entity")

        accounts, entities = get_bill_rule_form_options()
        names = [a.name for a in accounts]
        self.assertIn("Open Acct", names)
        self.assertNotIn("Closed Acct", names)
        self.assertIn("Some Entity", [e.name for e in entities])


class GetBillRulesTest(TestCase):
    def test_returns_all(self):
        save_bill_rule(cleaned(account_number="1"))
        save_bill_rule(cleaned(account_number="2"))
        self.assertEqual(len(get_bill_rules()), 2)
