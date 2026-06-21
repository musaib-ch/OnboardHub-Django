# Generated migration for document signatures

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import secrets


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_add_reminder_model'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentSignature',
            fields=[
                ('id', models.UUIDField(default=secrets.token_hex(16), editable=False, primary_key=True, serialize=False)),
                ('document_id', models.IntegerField()),
                ('signature_image', models.TextField(help_text='Base64-encoded signature image')),
                ('signature_type', models.CharField(choices=[('digital_pad', 'Digital Pad'), ('typed', 'Typed Name'), ('upload', 'Uploaded Image')], default='digital_pad', max_length=20)),
                ('signer_name', models.CharField(max_length=255)),
                ('signer_title', models.CharField(blank=True, max_length=255, null=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('signed_at', models.DateTimeField(auto_now_add=True)),
                ('consent_checked', models.BooleanField(default=False)),
                ('is_valid', models.BooleanField(default=True)),
                ('witness_signed_at', models.DateTimeField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='signatures', to=settings.AUTH_USER_MODEL)),
                ('witness_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='witnessed_signatures', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-signed_at'],
            },
        ),
        migrations.CreateModel(
            name='SignatureField',
            fields=[
                ('id', models.UUIDField(default=secrets.token_hex(16), editable=False, primary_key=True, serialize=False)),
                ('document_id', models.IntegerField()),
                ('field_type', models.CharField(choices=[('signature', 'Signature'), ('initial', 'Initial'), ('date', 'Date'), ('checkbox', 'Checkbox')], default='signature', max_length=20)),
                ('page_number', models.IntegerField(default=1)),
                ('x_position', models.FloatField(help_text='X coordinate (0-100%)')),
                ('y_position', models.FloatField(help_text='Y coordinate (0-100%)')),
                ('width', models.FloatField(default=30, help_text='Width in percentage')),
                ('height', models.FloatField(default=15, help_text='Height in percentage')),
                ('required_role', models.CharField(blank=True, help_text='Role required to sign', max_length=50)),
                ('optional', models.BooleanField(default=False)),
                ('signed', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('signature', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.documentsignature')),
            ],
            options={
                'ordering': ['page_number', 'y_position', 'x_position'],
            },
        ),
        migrations.AddIndex(
            model_name='documentsignature',
            index=models.Index(fields=['user', 'signed_at'], name='core_docume_user_id_signed_idx'),
        ),
        migrations.AddIndex(
            model_name='documentsignature',
            index=models.Index(fields=['document_id', 'signed_at'], name='core_docume_doc_id_signed_idx'),
        ),
        migrations.AddIndex(
            model_name='signaturefield',
            index=models.Index(fields=['document_id', 'page_number'], name='core_signat_doc_id_page_idx'),
        ),
    ]
