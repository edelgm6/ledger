# Generated by Django 4.1.6 on 2023-04-23 19:40

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0044_alter_account_sub_type'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='transaction',
            name='suggested_account',
        ),
        migrations.RemoveField(
            model_name='transaction',
            name='suggested_type',
        ),
    ]