# Back_Shkaf

Backend платформы обмена вещами и вторичного использования «Добрый Шкаф».

Стек: Python 3.14, Django 5.2, Django REST Framework, GeoDjango, SimpleJWT, drf-spectacular, PostgreSQL 16 + PostGIS, Docker, uv.

## Запуск через Docker

Основной способ: GeoDjango нужны системные библиотеки GDAL и GEOS, в Docker они уже установлены. Нужен только [Docker](https://www.docker.com/products/docker-desktop/).

### 1. Клонировать репозиторий

```bash
git clone https://github.com/H8TE228/Back_Shkaf.git
```

```bash
cd Back_Shkaf
```

### 2. Создать файл `.env`

Скопируйте `.env.example` в `.env` и заполните его. Значения для локальной разработки:

```
SECRET_KEY='<ключ>'
DEBUG=True
DB_NAME=shkaf
DB_USER=shkaf
DB_PASS=shkaf
DB_HOST=localhost
DB_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

Сгенерировать ключ можно командой ниже. Если в ключе есть символ `$`, замените его: Docker Compose воспринимает его как начало переменной.

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

`CORS_ALLOWED_ORIGINS` — адреса фронтенда через запятую.

### 3. Поднять проект

```bash
docker compose up --build
```

Команда запустит базу с PostGIS, применит миграции и запустит сервер на порту 8000. Код подключён к контейнеру, поэтому изменения подхватываются без пересборки. Пересборка нужна только при изменении зависимостей.

Если порт 5432 занят, укажите другой в `DB_PORT`.

### 4. Создать суперпользователя

Нужен для входа в админку. Выполняется во втором терминале:

```bash
docker compose exec web python manage.py createsuperuser
```

### Адреса

| Адрес | Что открывается |
|---|---|
| http://localhost:8000/api/v1/docs/ | Swagger UI |
| http://localhost:8000/api/v1/schema/ | Схема OpenAPI |
| http://localhost:8000/admin/ | Админка |

## Частые команды

Создать миграции после изменения моделей:

```bash
docker compose exec web python manage.py makemigrations
```

Применить миграции:

```bash
docker compose exec web python manage.py migrate
```

Запустить тесты:

```bash
docker compose exec web python manage.py test
```

Проверить код линтером:

```bash
docker compose exec web ruff check .
```

Остановить проект:

```bash
docker compose down
```

Остановить проект и удалить данные базы:

```bash
docker compose down -v
```

## Запуск без Docker

Понадобятся [uv](https://docs.astral.sh/uv/getting-started/installation/) (`pip install uv`), [GDAL и GEOS](https://docs.djangoproject.com/en/5.2/ref/contrib/gis/install/geolibs/) и PostgreSQL с PostGIS. Этот способ не проверялся на Windows.

Установить зависимости:

```bash
uv sync
```

Базу можно поднять из Docker:

```bash
docker compose up -d db
```

Если Django не находит библиотеки, укажите пути к ним в `.env` в переменных `GDAL_LIBRARY_PATH` и `GEOS_LIBRARY_PATH`. Запуск выполняется из папки `shkaf`:

```bash
uv run python manage.py migrate
```

```bash
uv run python manage.py runserver
```

## API

Префикс: `/api/v1`. Адреса указаны без завершающего слэша. Полное описание в Swagger.

| Метод | Адрес | Назначение | Доступ |
|---|---|---|---|
| POST | `/users/register` | Регистрация | Все |
| POST | `/users/login` | Вход, токены в куках | Все |
| POST | `/users/login/refresh` | Обновление токенов из куки | Все |
| POST | `/users/logout` | Выход, отзыв токена и удаление кук | Все |
| GET, PATCH, DELETE | `/me` | Личный кабинет | Авторизованные |
| PATCH | `/me/change-password` | Смена пароля | Авторизованные |
| GET | `/users/` | Список пользователей | Администраторы |
| PATCH, DELETE | `/users/{id}` | Изменение и удаление пользователя | Сам пользователь, администраторы |

| GET | `/me/items` | Все свои объявления, включая черновики и архив | Авторизованные |
| GET | `/items` | Каталог объявлений | Все |
| POST | `/items` | Создание объявления | Авторизованные |
| GET | `/items/{id}` | Объявление | Все, черновик и архив только владельцу |
| PUT, PATCH, DELETE | `/items/{id}` | Изменение и удаление | Владелец |
| POST | `/items/{id}/photos` | Загрузка фото, `multipart/form-data`, поле `image` | Владелец |
| DELETE | `/items/{id}/photos/{photo_id}` | Удаление фото | Владелец |
| GET | `/itemTypes`, `/itemTypes/{id}` | Справочник типов вещей | Все |
| GET | `/exchangePoints`, `/exchangePoints/{id}` | Каталог и карточка пункта обмена | Все |
| POST | `/exchangePoints` | Создание пункта с адресом | `is_staff` |
| PATCH | `/exchangePoints/{id}` | Изменение пункта и адреса | `is_staff` |

### Пункты обмена

Тестовые пункты в Екатеринбурге добавляет команда ниже: 10 активных, по одному в статусах `needs_check` и `closed`. Названия и контакты вымышлены, координаты приблизительные. Повторный запуск не создаёт дубли и не меняет уже существующие пункты.

```bash
docker compose exec web python manage.py seed_exchange_points
```


- В каталоге видны все статусы: `active`, `needs_check`, `closed`. По умолчанию новый пункт получает статус `needs_check`.
- Фильтры: `city`, `district`, `status`, `exchange_format` (`free`, `points`, `charity`), `item_type` (id типа вещи); `search` ищет по названию.
- `item_types` в ответе — типы вещей, которые принимает пункт. При создании и изменении они передаются списком id в `item_type_ids`.
- При создании передаётся объект `address` с полями `city`, `street`, `building`, `latitude`, `longitude` и необязательными полями адреса. При изменении координат нужно передать обе координаты.
- `opening_hours` — объект с днями `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`. Пустой объект означает неизвестное расписание, отсутствующий день — нет данных о нём, пустой список — выходной. Переданное при `PATCH` расписание заменяет прежнее целиком.
- Интервалы записываются как `{"from": "10:00", "to": "18:00"}`. `24:00` допустимо только как время окончания; ночную работу нужно разделить между днями. Интервалы одного дня не должны пересекаться.
- `verified_at`, `verified_by` и `picture` доступны только для чтения. Загрузка изображения через API пока не реализована.

### Объявления

- **Фильтры `/items` и `/me/items`:** `item_type`, `exchange_format`, `condition`, `status`, `district`.
- **Поиск и сортировка:** `search` ищет по названию и описанию, `ordering` принимает `created_at`, `updated_at` и варианты с минусом. По умолчанию сначала новые.
- **Каталог:** без `status` возвращает только активные объявления.
- **Значения полей:** `condition`: `new`, `good`, `used`. `exchange_format`: `free`, `swap`, `points`. `status`: `draft`, `active`, `reserved`, `given`, `archived`.
- **Статусы:** новое объявление создаётся как `draft` или `active`. Владелец может перевести `draft` в `active` и `active` в `archived`.
- **Резерв и передача:** статусы `reserved` и `given` назначает только передача вещи, а такое объявление нельзя менять или удалять.
- **Конфликты:** запрещённое действие со статусом отвечает 409.
- **Удаление:** объявление скрывается, но строка в базе остаётся.
- **Фото:** JPEG, PNG или WEBP, до 5 МБ, до 10 штук на объявление. Обложка — фото с наименьшим `position`.

### Авторизация через куки

Токены не передаются в теле ответа и недоступны JavaScript: сервер устанавливает их в HttpOnly-куках, а браузер сам отправляет куки с запросами. Заголовок `Authorization` не используется.

| Кука | Срок жизни | Путь |
|---|---|---|
| `access_token` | 10 часов | `/` |
| `refresh_token` | 7 дней | `/api/v1/users/` |

- Запросы с фронтенда нужно отправлять с `withCredentials: true`.
- Фронтенд и API должны быть на одном сайте. В разработке это обеспечивает прокси Vite.
- `POST /users/login` принимает `email` и `password`, а возвращает данные пользователя в том же формате, что и `/me`.
- `POST /users/login/refresh` вызывается без тела. Если он ответил 401, сессия закончилась и нужен повторный вход.
- `POST /users/register` создаёт пользователя, но куки не устанавливает: после него нужен вход.
- Флаг `Secure` включается при `DEBUG=False`, поэтому в продакшене нужен HTTPS.
- В Swagger достаточно выполнить `POST /users/login`: браузер сохранит куки и будет отправлять их сам.

## Модели данных

Модели следуют схеме ERD v2.

| Приложение | Модели |
|---|---|
| `users` | `User` |
| `exchange_points` | `Address` |
| `items` | `ItemType`, `Item`, `ItemPhoto` |

Удаление аккаунта не стирает строку в базе: персональные данные обезличиваются, а токены отзываются, чтобы сохранить историю передач.
