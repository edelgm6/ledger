# Generated by Django 4.1.6 on 2023-12-10 18:17

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0059_remove_prefill_transaction_prefill_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='prefill',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='api.prefill'),
        ),
    ]