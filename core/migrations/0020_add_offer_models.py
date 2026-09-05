# Generated manual migration to add offer-related models
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_employeestagepath_user_stage_path_stagetemplate_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='OfferFieldDefinition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('key', models.CharField(max_length=100)),
                ('field_type', models.CharField(default='string', max_length=30)),
                ('required', models.BooleanField(default=False)),
                ('visible_to', models.JSONField(default=list, blank=True)),
                ('order', models.IntegerField(default=0)),
                ('meta', models.JSONField(default=dict, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='offer_field_definitions', to='core.tenant')),
            ],
            options={
                'db_table': 'offer_field_definition',
                'ordering': ['order', 'name'],
                'unique_together': {('tenant', 'key')},
            },
        ),
        migrations.CreateModel(
            name='OfferTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('html_content', models.TextField(blank=True)),
                ('plain_text_preview', models.TextField(blank=True)),
                ('is_default', models.BooleanField(default=False)),
                ('variables_schema', models.JSONField(default=dict, blank=True)),
                ('attachments_allowed', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='offer_templates', to='core.tenant')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.user')),
            ],
            options={
                'db_table': 'offer_template',
                'ordering': ['-is_default', 'name'],
            },
        ),
        migrations.CreateModel(
            name='OfferEmailTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('subject_template', models.CharField(max_length=400)),
                ('html_body_template', models.TextField(blank=True)),
                ('plain_text_template', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='offer_email_templates', to='core.tenant')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.user')),
            ],
            options={
                'db_table': 'offer_email_template',
            },
        ),
        migrations.CreateModel(
            name='Offer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('candidate_name', models.CharField(max_length=200)),
                ('candidate_email', models.EmailField(max_length=200)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('pending_approval', 'Pending Approval'), ('sent', 'Sent'), ('accepted', 'Accepted'), ('rejected', 'Rejected'), ('revoked', 'Revoked'), ('expired', 'Expired')], default='draft', max_length=30)),
                ('rendered_html', models.TextField(blank=True)),
                ('rendered_email_html', models.TextField(blank=True)),
                ('total_compensation', models.DecimalField(null=True, max_digits=14, decimal_places=2, blank=True)),
                ('metadata', models.JSONField(default=dict, blank=True)),
                ('sent_at', models.DateTimeField(null=True, blank=True)),
                ('accepted_at', models.DateTimeField(null=True, blank=True)),
                ('rejected_at', models.DateTimeField(null=True, blank=True)),
                ('revoked_at', models.DateTimeField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='offers', to='core.tenant')),
                ('template', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.offertemplate')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='offers_created', to='core.user')),
                ('candidate_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='offers_received', to='core.user')),
            ],
            options={
                'db_table': 'offer',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='offer',
            index=models.Index(fields=['tenant', 'status'], name='core_offe_tenant_status_idx'),
        ),
        migrations.AddIndex(
            model_name='offer',
            index=models.Index(fields=['created_by'], name='core_offe_created_by_idx'),
        ),
        migrations.CreateModel(
            name='OfferFieldValue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('value', models.TextField(blank=True)),
                ('numeric_value', models.DecimalField(null=True, max_digits=14, decimal_places=2, blank=True)),
                ('date_value', models.DateField(null=True, blank=True)),
                ('field_definition', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.offerfielddefinition')),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='field_values', to='core.offer')),
            ],
            options={
                'db_table': 'offer_field_value',
            },
        ),
        migrations.CreateModel(
            name='OfferAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='offer_attachments/')),
                ('filename', models.CharField(max_length=255, null=True, blank=True)),
                ('content_type', models.CharField(max_length=100, null=True, blank=True)),
                ('size', models.IntegerField(null=True, blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('offer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='core.offer')),
                ('template', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='attachments_for_template', to='core.offertemplate')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.user')),
            ],
            options={
                'db_table': 'offer_attachment',
            },
        ),
        migrations.CreateModel(
            name='OfferStatusHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('from_status', models.CharField(max_length=50)),
                ('to_status', models.CharField(max_length=50)),
                ('reason', models.TextField(blank=True)),
                ('comment', models.TextField(blank=True)),
                ('timestamp', models.DateTimeField(default=django.utils.timezone.now)),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.user')),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='status_history', to='core.offer')),
            ],
            options={
                'db_table': 'offer_status_history',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.CreateModel(
            name='OfferApproval',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.IntegerField(default=0)),
                ('status', models.CharField(default='pending', max_length=20)),
                ('comment', models.TextField(blank=True)),
                ('acted_at', models.DateTimeField(null=True, blank=True)),
                ('approver', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.user')),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='approvals', to='core.offer')),
            ],
            options={
                'db_table': 'offer_approval',
                'ordering': ['order'],
            },
        ),
        migrations.CreateModel(
            name='OfferSignature',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('signer_name', models.CharField(max_length=200)),
                ('signature_blob', models.TextField(blank=True)),
                ('signature_method', models.CharField(default='typed', max_length=50)),
                ('signed_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('ip_address', models.CharField(max_length=45, blank=True)),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='signatures', to='core.offer')),
            ],
            options={
                'db_table': 'offer_signature',
            },
        ),
        migrations.CreateModel(
            name='OfferSendToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(default='', max_length=128, unique=True)),
                ('token_type', models.CharField(default='view', max_length=30)),
                ('expires_at', models.DateTimeField(null=True, blank=True)),
                ('used', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tokens', to='core.offer')),
            ],
            options={
                'db_table': 'offer_send_token',
            },
        ),
        migrations.CreateModel(
            name='OfferExport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('export_type', models.CharField(max_length=20)),
                ('storage_key', models.CharField(max_length=500)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.user')),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exports', to='core.offer')),
            ],
            options={
                'db_table': 'offer_export',
            },
        ),
        migrations.CreateModel(
            name='OfferAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(max_length=200)),
                ('details', models.JSONField(default=dict, blank=True)),
                ('timestamp', models.DateTimeField(default=django.utils.timezone.now)),
                ('performed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.user')),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='audit_logs', to='core.offer')),
            ],
            options={
                'db_table': 'offer_audit_log',
                'ordering': ['-timestamp'],
            },
        ),
        migrations.CreateModel(
            name='OfferVisibility',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(max_length=100, null=True, blank=True)),
                ('permission_type', models.CharField(default='view', max_length=30)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.user')),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='visibility', to='core.offer')),
            ],
            options={
                'db_table': 'offer_visibility',
            },
        ),
        # Create a small data migration to add custom permission codenames
        migrations.RunPython(code=lambda apps, schema_editor: None, reverse_code=lambda apps, schema_editor: None),
    ]
