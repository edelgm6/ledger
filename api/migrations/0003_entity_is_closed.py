# Generated by Django 5.1.4 on 2025-02-02 00:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="entity",
            name="is_closed",
            field=models.BooleanField(default=False),
        ),
    ]
