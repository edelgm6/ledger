# Generated by Django 4.1.6 on 2024-07-18 10:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0076_docsearch_journal_entry_item_type_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docsearch',
            name='journal_entry_item_type',
            field=models.CharField(choices=[('debit', 'Debit'), ('credit', 'Credit')], max_length=25),
        ),
    ]