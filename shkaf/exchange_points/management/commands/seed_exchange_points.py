from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from exchange_points.models import ExchangePoint
from exchange_points.serializers import ExchangePointSerializer
from items.models import ItemType

WEEKDAYS = ('mon', 'tue', 'wed', 'thu', 'fri')


def schedule(weekdays, saturday=None, sunday=None):
    hours = {day: [{'from': weekdays[0], 'to': weekdays[1]}] for day in WEEKDAYS}
    hours['sat'] = [{'from': saturday[0], 'to': saturday[1]}] if saturday else []
    hours['sun'] = [{'from': sunday[0], 'to': sunday[1]}] if sunday else []
    return hours


CLOTHES = ['Детская одежда', 'Взрослая одежда', 'Обувь']
ALL_TYPES = ['Детская одежда', 'Взрослая одежда', 'Обувь', 'Игрушки', 'Книги', 'Мебель']

# Тестовые пункты в Екатеринбурге: названия и контакты вымышлены, координаты приблизительные
POINTS = [
    ('Добрый шкаф на Втузгородке', 'Кировский', 'Мира', '19', 56.8440, 60.6522,
     ['free', 'charity'], CLOTHES + ['Игрушки'], schedule(('10:00', '19:00'), ('11:00', '16:00'))),
    ('Обменник «Вторая жизнь вещей»', 'Ленинский', 'Вайнера', '9', 56.8346, 60.6006,
     ['free', 'points'], ALL_TYPES, schedule(('09:00', '21:00'), ('10:00', '20:00'), ('10:00', '18:00'))),
    ('Детский шкаф на 8 Марта', 'Ленинский', '8 Марта', '46', 56.8263, 60.6040,
     ['free'], ['Детская одежда', 'Игрушки', 'Книги'], schedule(('11:00', '20:00'), ('11:00', '17:00'))),
    ('Благотворительный пункт на ВИЗе', 'Верх-Исетский', 'Крауля', '44', 56.8370, 60.5530,
     ['charity'], CLOTHES, schedule(('10:00', '18:00'))),
    ('Пункт обмена на Уралмаше', 'Орджоникидзевский', 'Космонавтов', '18', 56.8790, 60.6100,
     ['free', 'points'], CLOTHES + ['Мебель'], schedule(('10:00', '19:00'), ('10:00', '15:00'))),
    ('Контейнер для текстиля на Эльмаше', 'Орджоникидзевский', 'Корепина', '4', 56.8930, 60.6440,
     ['charity'], ['Взрослая одежда', 'Обувь'], schedule(('00:00', '24:00'), ('00:00', '24:00'), ('00:00', '24:00'))),
    ('Книжный обмен в Пионерском', 'Кировский', 'Уральская', '57', 56.8550, 60.6390,
     ['free', 'points'], ['Книги', 'Игрушки'], schedule(('12:00', '20:00'), ('12:00', '18:00'))),
    ('Добрый шкаф на ЖБИ', 'Кировский', 'Сыромолотова', '11', 56.8510, 60.6920,
     ['free', 'charity'], CLOTHES, schedule(('10:00', '18:00'), ('10:00', '14:00'))),
    ('Обменный пункт на Сортировке', 'Железнодорожный', 'Технологическая', '4', 56.8650, 60.5350,
     ['points'], ALL_TYPES, schedule(('09:00', '18:00'))),
    ('Шкаф взаимопомощи на Юго-Западном', 'Ленинский', 'Белореченская', '17', 56.8130, 60.5550,
     ['free', 'charity'], CLOTHES + ['Игрушки'], schedule(('10:00', '19:00'), ('11:00', '16:00'))),
    ('Мебельный обмен на Ботанике', 'Чкаловский', 'Шварца', '2', 56.7930, 60.6290,
     ['free', 'points'], ['Мебель'], schedule(('10:00', '20:00'), ('10:00', '18:00')), 'needs_check'),
    ('Пункт приёма на Химмаше', 'Чкаловский', 'Грибоедова', '4', 56.7470, 60.6350,
     ['charity'], CLOTHES, schedule(('10:00', '17:00')), 'closed'),
]


class Command(BaseCommand):
    help = 'Добавляет тестовые пункты обмена в Екатеринбурге. Уже существующие пункты с тем же названием не меняются.'

    @transaction.atomic
    def handle(self, *args, **options):
        types = dict(ItemType.objects.values_list('title', 'pk'))
        created = 0
        for number, (title, district, street, building, latitude, longitude, formats, type_titles, hours, *rest) in \
                enumerate(POINTS, start=1):
            if ExchangePoint.objects.filter(title=title).exists():
                continue
            serializer = ExchangePointSerializer(data={
                'title': title,
                'description': 'Тестовый пункт обмена для разработки и демонстрации.',
                'address': {
                    'region': 'Свердловская область', 'city': 'Екатеринбург', 'district': district,
                    'street': street, 'building': building, 'latitude': latitude, 'longitude': longitude,
                },
                'opening_hours': hours,
                'phone': f'+7900000{number:04d}',
                'email': f'point{number}@example.test',
                'formats': formats,
                'item_type_ids': [types[type_title] for type_title in type_titles],
                'status': rest[0] if rest else ExchangePoint.Status.ACTIVE,
            })
            if not serializer.is_valid():
                raise CommandError(f'{title}: {serializer.errors}')
            serializer.save()
            created += 1
        self.stdout.write(self.style.SUCCESS(
            f'Создано пунктов: {created}, всего в базе: {ExchangePoint.objects.count()}'
        ))
