from decimal import Decimal

from django.db import migrations

# Пилотные ориентиры: средняя масса вещи и кг CO₂e на кг этой категории.
FACTORS = {
    'Детская одежда': ('0.30', '4.00'),
    'Взрослая одежда': ('0.50', '4.00'),
    'Обувь': ('0.80', '6.00'),
    'Игрушки': ('0.40', '2.00'),
    'Книги': ('0.45', '1.00'),
    'Мебель': ('12.00', '1.50'),
}


def seed_factors(apps, schema_editor):
    types = apps.get_model('items', 'ItemType').objects.using(schema_editor.connection.alias)
    for title, (weight, co2) in FACTORS.items():
        types.filter(title=title, avg_weight_kg__isnull=True).update(avg_weight_kg=Decimal(weight))
        types.filter(title=title, co2_per_kg__isnull=True).update(co2_per_kg=Decimal(co2))


class Migration(migrations.Migration):
    dependencies = [('items', '0003_seed_item_types')]
    operations = [migrations.RunPython(seed_factors, migrations.RunPython.noop)]
