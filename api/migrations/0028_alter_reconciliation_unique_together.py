# Generated by Django 4.1.6 on 2023-03-01 23:29

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_reconciliation'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='reconciliation',
            unique_together={('account', 'date')},
        ),
    ]