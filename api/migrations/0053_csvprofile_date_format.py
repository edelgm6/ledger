# Generated by Django 4.1.6 on 2023-08-02 20:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0052_remove_csvprofile_account_remove_csvprofile_amount'),
    ]

    operations = [
        migrations.AddField(
            model_name='csvprofile',
            name='date_format',
            field=models.CharField(default='%Y-%m-%d', max_length=200),
        ),
    ]
