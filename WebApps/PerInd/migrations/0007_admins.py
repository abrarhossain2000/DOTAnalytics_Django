# Generated by Django 2.2.14 on 2020-08-28 20:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('PerInd', '0006_auto_20200817_1607'),
    ]

    operations = [
        migrations.CreateModel(
            name='Admins',
            fields=[
                ('admin_id', models.AutoField(db_column='Admin_ID', primary_key=True, serialize=False)),
                ('active', models.BooleanField(db_column='Active')),
            ],
            options={
                'db_table': 'Admins',
                'managed': False,
            },
        ),
    ]