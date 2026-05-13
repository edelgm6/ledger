from django.db import migrations, models


def rename_purchases_to_operating(apps, schema_editor):
    Account = apps.get_model('api', 'Account')
    Account.objects.filter(sub_type='purchases').update(sub_type='operating')


def reverse_rename(apps, schema_editor):
    Account = apps.get_model('api', 'Account')
    Account.objects.filter(sub_type='operating').update(sub_type='purchases')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0024_add_depreciation_subtype'),
    ]

    operations = [
        migrations.RunPython(rename_purchases_to_operating, reverse_rename),
        migrations.AlterField(
            model_name='account',
            name='sub_type',
            field=models.CharField(choices=[('short_term_debt', 'Short-term Debt'), ('taxes_payable', 'Taxes Payable'), ('long_term_debt', 'Long-term Debt'), ('cash', 'Cash'), ('accounts_receivable', 'Accounts Receivable'), ('prepaid_expenses', 'Prepaid Expenses'), ('securities_unrestricted', 'Securities-Unrestricted'), ('securities_retirement', 'Securities-Retirement'), ('real_estate', 'Real Estate'), ('vehicles', 'Vehicles'), ('retained_earnings', 'Retained Earnings'), ('salary', 'Salary'), ('dividends_and_interest', 'Dividends & Interest'), ('realized_investment_gains', 'Realized Investment Gains'), ('other_income', 'Other Income'), ('unrealized_investment_gains', 'Unrealized Investment Gains'), ('operating', 'Operating'), ('tax', 'Tax'), ('interest', 'Interest Expense'), ('depreciation', 'Depreciation')], max_length=30),
        ),
    ]
