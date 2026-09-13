"""Repair Account rows whose `type` disagrees with `sub_type`.

`type` is now derived from `sub_type` in Account.save(), but that only governs
future writes. Rows already stored with a contradictory pair keep it until
repaired here, and a contradictory row is not cosmetic: it double-counts into
the wrong statement section (Statement.get_summaries credits both the type and
the sub_type bucket) and is silently dropped from its own, because
iter_sub_type_buckets only walks the sub_types SUBTYPE_TO_TYPE_MAP lists under
that type.

The map is duplicated here rather than imported from api.models: migrations must
keep working if the model's map is later edited, and a data migration has to
describe the world as it was when written.
"""

from django.db import migrations

SUBTYPE_TO_TYPE = {
    "short_term_debt": "liability",
    "taxes_payable": "liability",
    "long_term_debt": "liability",
    "cash": "asset",
    "accounts_receivable": "asset",
    "prepaid_expenses": "asset",
    "securities_unrestricted": "asset",
    "securities_restricted": "asset",
    "real_estate": "asset",
    "vehicles": "asset",
    "retained_earnings": "equity",
    "salary": "income",
    "dividends_and_interest": "income",
    "realized_investment_gains": "income",
    "other_income": "income",
    "unrealized_investment_gains": "income",
    "operating": "expense",
    "interest": "expense",
    "tax": "expense",
}


def forwards(apps, schema_editor):
    Account = apps.get_model("api", "Account")
    for sub_type, expected in SUBTYPE_TO_TYPE.items():
        Account.objects.filter(sub_type=sub_type).exclude(type=expected).update(
            type=expected
        )


def backwards(apps, schema_editor):
    # The prior (contradictory) values are not recoverable, and restoring them
    # would reintroduce the mis-sectioning. Rolling back leaves the rows
    # repaired, which is consistent with any schema this migration precedes.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0050_remove_s3file_analysis_complete"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
