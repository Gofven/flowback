# Generated by Django 4.2.7 on 2024-06-11 15:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('poll', '0035_pollpredictionstatement_blockchain_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='pollpredictionbet',
            name='blockchain_id',
            field=models.IntegerField(blank=True, default=None, null=True),
        ),
    ]
