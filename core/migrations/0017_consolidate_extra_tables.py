# Generated migration - consolidate Stage, Reminder, DocumentSignature, SignatureField into JSON

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_add_content_filtering'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Stage',
        ),
        migrations.DeleteModel(
            name='Reminder',
        ),
        migrations.DeleteModel(
            name='SignatureField',
        ),
        migrations.DeleteModel(
            name='DocumentSignature',
        ),
    ]
