# Generated by Django 4.1.6 on 2024-07-28 11:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0083_alter_journalentryitem_entity'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='entity',
            options={'verbose_name_plural': 'entities'},
        ),
        migrations.AlterField(
            model_name='entity',
            name='name',
            field=models.CharField(max_length=200, unique=True),
        ),
    ]