# Generated by Django 4.2.7 on 2024-09-12 13:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kanban', '0006_kanbanentry_attachments'),
    ]

    operations = [
        migrations.AddField(
            model_name='kanbanentry',
            name='category',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
