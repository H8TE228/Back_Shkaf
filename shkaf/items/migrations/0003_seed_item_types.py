from django.db import migrations

# Типы вещей из ТЗ. Коэффициенты для экотрекера заполняются в задаче 2.45.
ITEM_TYPES = ['Детская одежда', 'Взрослая одежда', 'Обувь', 'Игрушки', 'Книги', 'Мебель']


def seed_item_types(apps, schema_editor):
    ItemType = apps.get_model('items', 'ItemType')
    for title in ITEM_TYPES:
        ItemType.objects.get_or_create(title=title)


class Migration(migrations.Migration):

    dependencies = [
        ('items', '0002_alter_itemphoto_image'),
    ]

    operations = [
        migrations.RunPython(seed_item_types, migrations.RunPython.noop),
    ]
