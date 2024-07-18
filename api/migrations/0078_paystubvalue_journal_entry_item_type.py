# Generated by Django 4.1.6 on 2024-07-18 11:00

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0077_alter_docsearch_journal_entry_item_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='paystubvalue',
            name='journal_entry_item_type',
            field=models.CharField(choices=[('debit', 'Debit'), ('credit', 'Credit')], default='debit', max_length=25),
            preserve_default=False,
        ),
    ]
