# Generated by Django 4.1.6 on 2024-07-26 11:20

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0082_entity_alter_docsearch_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='journalentryitem',
            name='entity',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='journal_entry_items', to='api.entity'),
        ),
    ]