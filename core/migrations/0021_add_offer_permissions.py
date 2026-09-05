from django.db import migrations


def create_offer_permissions(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    # ContentType for core app — attach to the Offer model content type if available, else to core app generic
    try:
        offer_ct = ContentType.objects.get(app_label='core', model='offer')
    except ContentType.DoesNotExist:
        # fallback to core app label only (create a content type for 'offer' will be present after makemigrations)
        offer_ct = None

    perms = [
        ('send_offer', 'Can send offers'),
        ('revoke_offer', 'Can revoke offers'),
        ('export_offer', 'Can export offers'),
        ('manage_templates', 'Can manage offer templates'),
        ('manage_email_templates', 'Can manage offer email templates'),
        ('manage_offer_fields', 'Can manage offer fields'),
        ('view_offer_analytics', 'Can view offer analytics'),
        ('approve_offer', 'Can approve offers'),
    ]

    for codename, name in perms:
        if offer_ct:
            Permission.objects.get_or_create(codename=codename, name=name, content_type=offer_ct)
        else:
            # If Offer content type is not present yet, attach to core.Tenant as a reasonable default
            try:
                tenant_ct = ContentType.objects.get(app_label='core', model='tenant')
                Permission.objects.get_or_create(codename=codename, name=name, content_type=tenant_ct)
            except ContentType.DoesNotExist:
                # Last resort: skip creating permission; it will be created later manually
                pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_add_offer_models'),
    ]

    operations = [
        migrations.RunPython(create_offer_permissions, reverse_code=migrations.RunPython.noop),
    ]
