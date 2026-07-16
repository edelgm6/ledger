from django.db import migrations, models


def rename_retirement_to_restricted(apps, schema_editor):
    Account = apps.get_model('api', 'Account')
    Account.objects.filter(sub_type='securities_retirement').update(
        sub_type='securities_restricted'
    )


def reverse_rename(apps, schema_editor):
    Account = apps.get_model('api', 'Account')
    Account.objects.filter(sub_type='securities_restricted').update(
        sub_type='securities_retirement'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0037_recharacterizechange_recharacterizechangeitem'),
    ]

    operations = [
        migrations.RunPython(rename_retirement_to_restricted, reverse_rename),
        migrations.AlterField(
            model_name='account',
            name='sub_type',
            field=models.CharField(choices=[('short_term_debt', 'Short-term Debt'), ('taxes_payable', 'Taxes Payable'), ('long_term_debt', 'Long-term Debt'), ('cash', 'Cash'), ('accounts_receivable', 'Accounts Receivable'), ('prepaid_expenses', 'Prepaid Expenses'), ('securities_unrestricted', 'Securities-Unrestricted'), ('securities_restricted', 'Securities-Restricted'), ('real_estate', 'Real Estate'), ('vehicles', 'Vehicles'), ('retained_earnings', 'Retained Earnings'), ('salary', 'Salary'), ('dividends_and_interest', 'Dividends & Interest'), ('realized_investment_gains', 'Realized Investment Gains'), ('other_income', 'Other Income'), ('unrealized_investment_gains', 'Unrealized Investment Gains'), ('operating', 'Operating'), ('tax', 'Tax'), ('interest', 'Interest Expense')], max_length=30),
        ),
    ]
