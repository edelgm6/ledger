# Generated by Django 4.1.6 on 2023-02-22 00:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_alter_account_csv_profile_alter_account_sub_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='category',
            field=models.CharField(blank=True, max_length=200),
        ),
    ]