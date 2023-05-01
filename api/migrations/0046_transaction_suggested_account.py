# Generated by Django 4.1.6 on 2023-05-01 21:35

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0045_remove_transaction_suggested_account_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='suggested_account',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='suggested_account', to='api.account'),
        ),
    ]
