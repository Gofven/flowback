# Generated by Django 4.2.7 on 2024-06-19 13:08

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('files', '0002_filesegment_name'),
        ('group', '0032_group_blockchain_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupthread',
            name='attachments',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='files.filecollection'),
        ),
    ]