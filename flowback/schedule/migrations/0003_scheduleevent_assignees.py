# Generated by Django 4.2.7 on 2024-11-13 12:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('group', '0041_grouppermissions_send_group_email'),
        ('schedule', '0002_scheduleevent_work_group'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduleevent',
            name='assignees',
            field=models.ManyToManyField(to='group.groupuser'),
        ),
    ]