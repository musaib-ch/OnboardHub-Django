from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_alter_content_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="medicalrecord",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
