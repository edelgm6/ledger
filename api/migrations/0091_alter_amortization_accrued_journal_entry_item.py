# Generated by Django 4.1.6 on 2024-08-13 15:49

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0090_alter_transaction_amortization'),
    ]

    operations = [
        migrations.AlterField(
            model_name='amortization',
            name='accrued_journal_entry_item',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='amortization', to='api.journalentryitem'),
        ),
    ]
