from django.db import migrations


def enable_approved_stores(apps, schema_editor):
    Business = apps.get_model("businesses", "Business")
    Application = apps.get_model("businesses", "BusinessApplication")
    AuditEvent = apps.get_model("businesses", "AuditEvent")
    approved_ids = (
        Application.objects.using(schema_editor.connection.alias)
        .filter(status="approved", business__isnull=False)
        .values_list("business_id", flat=True)
    )
    for business in Business.objects.using(schema_editor.connection.alias).filter(
        pk__in=approved_ids, provisioning_status="ready", suspended=False, published=False
    ):
        business.published = True
        business.save(update_fields=["published"], using=schema_editor.connection.alias)
        AuditEvent.objects.using(schema_editor.connection.alias).create(
            business_id=business.pk,
            action="store.online_on_approval_enabled",
            object_id=str(business.pk),
        )


class Migration(migrations.Migration):
    dependencies = [("businesses", "0001_initial")]
    operations = [migrations.RunPython(enable_approved_stores, migrations.RunPython.noop)]
