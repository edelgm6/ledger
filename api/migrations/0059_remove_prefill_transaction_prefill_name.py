# Generated by Django 4.1.6 on 2023-12-10 18:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0058_prefill_prefillitem_autotag_prefill'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='prefill',
            name='transaction',
        ),
        migrations.AddField(
            model_name='prefill',
            name='name',
            field=models.CharField(default='whatever', max_length=200),
            preserve_default=False,
        ),
    ]
