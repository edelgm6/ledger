# Generated by Django 4.1.6 on 2023-12-17 15:08

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0060_transaction_prefill'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='taxcharge',
            unique_together={('type', 'date')},
        ),
    ]