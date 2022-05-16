# Generated by Django 3.2.12 on 2022-05-12 15:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0030_auto_20220207_1209'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='contentmetadata',
            name='catalog_query_mapping',
        ),
        migrations.AddField(
            model_name='contentmetadata',
            name='catalog_queries',
            field=models.ManyToManyField(to='catalog.CatalogQuery'),
        ),
        migrations.DeleteModel(
            name='ContentMetadataToQueries',
        ),
    ]
