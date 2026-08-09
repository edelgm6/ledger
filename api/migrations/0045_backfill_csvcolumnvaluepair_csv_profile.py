from django.db import migrations


def backfill_csv_profile(apps, schema_editor):
    """Move each CSVProfile's M2M-linked pairs onto the new per-profile FK.

    Give every profile its own copy of each pair it was linked to (handling the
    unexpected case where a pair was shared across profiles), then drop the
    originals — which still have a null FK, along with any never-linked orphans.
    """
    CSVProfile = apps.get_model("api", "CSVProfile")
    CSVColumnValuePair = apps.get_model("api", "CSVColumnValuePair")

    for profile in CSVProfile.objects.all():
        for pair in profile.clear_values_column_pairs.all():
            CSVColumnValuePair.objects.create(
                column=pair.column,
                value=pair.value,
                csv_profile=profile,
            )

    # Originals were never assigned an FK; this also sweeps up true orphans.
    CSVColumnValuePair.objects.filter(csv_profile__isnull=True).delete()


def rebuild_m2m(apps, schema_editor):
    """Reverse: repopulate the M2M through-table from the FK."""
    CSVColumnValuePair = apps.get_model("api", "CSVColumnValuePair")

    for pair in CSVColumnValuePair.objects.filter(csv_profile__isnull=False):
        pair.csv_profile.clear_values_column_pairs.add(pair)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0044_add_csvcolumnvaluepair_csv_profile"),
    ]

    operations = [
        migrations.RunPython(backfill_csv_profile, rebuild_m2m),
    ]
