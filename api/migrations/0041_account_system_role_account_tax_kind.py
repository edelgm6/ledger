from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0040_delete_prefillitem'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='system_role',
            field=models.CharField(
                blank=True,
                choices=[
                    ('wallet', 'Wallet'),
                    ('starting_equity', 'Starting Equity'),
                    ('unrealized_gains_and_losses', 'Unrealized Gains and Losses'),
                    ('prepaid_expenses', 'Prepaid Expenses'),
                ],
                max_length=30,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='account',
            name='tax_kind',
            field=models.CharField(
                blank=True,
                choices=[
                    ('federal', 'Federal'),
                    ('state', 'State'),
                    ('property', 'Property'),
                    ('payroll', 'Payroll'),
                ],
                max_length=10,
                null=True,
            ),
        ),
    ]
