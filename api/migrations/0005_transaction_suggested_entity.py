# Generated by Django 5.1.4 on 2025-02-02 01:07

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_autotag_entity'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='suggested_entity',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='suggested_entity', to='api.entity'),
        ),
    ]
