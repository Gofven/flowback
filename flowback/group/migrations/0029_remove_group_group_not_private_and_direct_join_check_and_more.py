# Generated by Django 4.2.7 on 2024-05-29 12:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('group', '0028_grouppermissions_prediction_bet_create_and_more'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='group',
            name='group_not_private_and_direct_join_check',
        ),
        migrations.AddConstraint(
            model_name='group',
            constraint=models.CheckConstraint(check=models.Q(models.Q(('public', False), ('direct_join', True)), _negated=True), name='group_not_public_and_direct_join_check'),
        ),
    ]
