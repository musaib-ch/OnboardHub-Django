# Generated manual migration: add offer.email_template FK
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_add_offer_permissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='offer',
            name='email_template',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='offers_using_email_template', to='core.offeremailtemplate'),
        ),
    ]
