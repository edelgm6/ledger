# Generated by Django 4.1.6 on 2023-03-02 22:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0028_alter_reconciliation_unique_together'),
    ]

    operations = [
        migrations.AlterField(
            model_name='account',
            name='sub_type',
            field=models.CharField(choices=[('short_term_debt', 'Short-term Debt'), ('long_term_debt', 'Long-term Debt'), ('cash', 'Cash'), ('real_estate', 'Real Estate'), ('securities_retirement', 'Securities-Retirement'), ('securities_unrestricted', 'Securities-Unrestricted'), ('retained_earnings', 'Retained Earnings'), ('investment_gains', 'Investment Gains'), ('income', 'Income'), ('expense', 'Expense')], max_length=30),
        ),
    ]