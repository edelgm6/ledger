"""Reconcile S3File rows that encode "done" two different ways.

S3File carried two independent encodings of completion: the `analysis_complete`
timestamp and the `status` field. Contradictory rows already exist -- the seed
command and two test fixtures set the timestamp while leaving status at its
PENDING default -- so `status` cannot simply become authoritative without first
repairing them.

This migration must run *before* the code that treats `status` as the single
source of truth ships, which is why the column drop is a separate, later
migration.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    S3File = apps.get_model("api", "S3File")
    # A timestamp means extraction finished. Only advance rows still sitting at
    # a non-terminal status: an explicit FAILED is a real signal about the last
    # attempt and must not be overwritten by a stale timestamp.
    S3File.objects.filter(
        analysis_complete__isnull=False,
        status__in=["PENDING", "PROCESSING"],
    ).update(status="COMPLETE")


def backwards(apps, schema_editor):
    # Re-deriving the timestamp is not possible -- it recorded when extraction
    # finished, which this migration does not know. Rolling back leaves status
    # as repaired, which is a strict improvement over the contradictory state.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0048_remove_s3file_textract_job_id"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
