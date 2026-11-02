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
| POST | `/users/auth` | Вход, выдача JWT | Все |
| POST | `/users/auth/refresh` | Обновление токена | Все |
| POST | `/users/logout` | Выход, отзыв refresh-токена | Авторизованные |
| GET, PATCH, DELETE | `/me` | Личный кабинет | Авторизованные |
| PATCH | `/me/change-password` | Смена пароля | Авторизованные |
| GET | `/users/` | Список пользователей | Администраторы |
| PATCH, DELETE | `/users/{id}` | Изменение и удаление пользователя | Сам пользователь, администраторы |

## Модели данных

Модели следуют схеме ERD v2.

| Приложение | Модели |
|---|---|
| `users` | `User` |
| `exchange_points` | `Address` |
| `items` | `ItemType`, `Item`, `ItemPhoto` |

Удаление аккаунта не стирает строку в базе: персональные данные обезличиваются, а токены отзываются, чтобы сохранить историю передач.
