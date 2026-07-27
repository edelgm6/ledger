from django.db import migrations

# special_type values that carry over verbatim as system_role.
SYSTEM_ROLE_VALUES = frozenset(
    {"wallet", "starting_equity", "unrealized_gains_and_losses", "prepaid_expenses"}
)

# special_type value -> tax_kind value (a real rename, unlike the roles above).
SPECIAL_TYPE_TO_TAX_KIND = {
    "federal_taxes": "federal",
    "state_taxes": "state",
    "property_taxes": "property",
    "payroll_taxes": "payroll",
}

# tax_kind value -> the *_taxes_payable special_type, for reversing the payable
# markers that are otherwise reachable only via the tax_payable_account FK.
TAX_KIND_TO_PAYABLE_SPECIAL_TYPE = {
    "federal": "federal_taxes_payable",
    "state": "state_taxes_payable",
    "property": "property_taxes_payable",
}


def forwards(apps, schema_editor):
    Account = apps.get_model("api", "Account")
    for account in Account.objects.exclude(special_type__isnull=True):
        st = account.special_type
        if st in SYSTEM_ROLE_VALUES:
            account.system_role = st
            account.save(update_fields=["system_role"])
        elif st in SPECIAL_TYPE_TO_TAX_KIND:
            account.tax_kind = SPECIAL_TYPE_TO_TAX_KIND[st]
            account.save(update_fields=["tax_kind"])
        # *_taxes_payable markers are intentionally dropped (payable accounts are
        # reached via a tax account's tax_payable_account FK).


def backwards(apps, schema_editor):
    Account = apps.get_model("api", "Account")

    kind_to_special = {v: k for k, v in SPECIAL_TYPE_TO_TAX_KIND.items()}

    for account in Account.objects.all():
        if account.system_role in SYSTEM_ROLE_VALUES:
            account.special_type = account.system_role
            account.save(update_fields=["special_type"])
        elif account.tax_kind in kind_to_special:
            account.special_type = kind_to_special[account.tax_kind]
            account.save(update_fields=["special_type"])
            # Restore the payable account's marker from the FK link.
            payable = account.tax_payable_account
            payable_special = TAX_KIND_TO_PAYABLE_SPECIAL_TYPE.get(account.tax_kind)
            if payable is not None and payable_special is not None:
                payable.special_type = payable_special
                payable.save(update_fields=["special_type"])


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0041_account_system_role_account_tax_kind'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
