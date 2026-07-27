from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0042_migrate_special_type_to_role_and_kind'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='account',
            name='unique_special_type_except_property_taxes',
        ),
        migrations.RemoveField(
            model_name='account',
            name='special_type',
        ),
        migrations.AddConstraint(
            model_name='account',
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    (
                        'system_role__in',
                        ['wallet', 'starting_equity', 'unrealized_gains_and_losses'],
                    )
                ),
                fields=('system_role',),
                name='unique_singleton_system_role',
            ),
        ),
        migrations.AddConstraint(
            model_name='account',
            constraint=models.UniqueConstraint(
                condition=models.Q(('tax_kind__in', ['federal', 'state'])),
                fields=('tax_kind',),
                name='unique_federal_state_tax_kind',
            ),
        ),
    ]
