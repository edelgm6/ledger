# Generated by Django 4.1.6 on 2024-07-16 14:47

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0074_paystub_docsearch_prefill_s3file_prefill_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='docsearch',
            name='prefill',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='api.prefill'),
        ),
    ]