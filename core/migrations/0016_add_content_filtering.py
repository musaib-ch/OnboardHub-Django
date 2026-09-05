# Generated migration for content filtering fields (Phase 3 - JSON consolidated)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0015_add_signature_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='content',
            name='target_roles',
            field=models.JSONField(blank=True, default=list, help_text='Roles: admin, hrbp, manager, employee (empty = all)'),
        ),
        migrations.AddField(
            model_name='content',
            name='target_locations',
            field=models.JSONField(blank=True, default=list, help_text='Location IDs (empty = all)'),
        ),
        migrations.AddField(
            model_name='content',
            name='target_departments',
            field=models.JSONField(blank=True, default=list, help_text='Department IDs (empty = all)'),
        ),
        migrations.AddField(
            model_name='content',
            name='target_divisions',
            field=models.JSONField(blank=True, default=list, help_text='Division IDs (empty = all)'),
        ),
        migrations.AddField(
            model_name='content',
            name='prerequisite_content',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='unlocks', to='core.content'),
        ),
        migrations.AddField(
            model_name='content',
            name='sequence_order',
            field=models.IntegerField(default=0, help_text='Order in learning path'),
        ),
    ]
