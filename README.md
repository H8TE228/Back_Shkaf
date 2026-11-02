# Back_Shkaf

Backend платформы обмена вещами и вторичного использования «Добрый Шкаф».

Стек: Python 3.13+, Django 5.2, Django REST Framework, SimpleJWT, drf-spectacular, PostgreSQL 16 + PostGIS, uv.

## Что нужно установить

- [Python](https://www.python.org/downloads/) 3.13 или новее
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (можно через `pip install uv`)
- [Docker](https://www.docker.com/products/docker-desktop/)

## Установка

Команды выполняются из корня репозитория, если не указано другое.

### 1. Клонировать репозиторий

```bash
git clone https://github.com/H8TE228/Back_Shkaf.git
```

```bash
cd Back_Shkaf
```

### 2. Установить зависимости и активировать окружение

```bash
uv sync
```

Если uv не может установить Python 3.14, указанный в `.python-version`, соберите окружение на 3.13:

```bash
uv sync --python 3.13
```

Активация окружения в Windows (PowerShell):

```powershell
.venv\Scripts\Activate.ps1
```

Активация в Linux и macOS:

```bash
source .venv/bin/activate
```

### 3. Создать файл `.env`

Скопируйте `.env.example` в `.env` в корне репозитория и заполните его. Значения для локальной разработки:

```
SECRET_KEY=<ключ>
DEBUG=True
DB_NAME=shkaf
DB_USER=shkaf
DB_PASS=shkaf
DB_HOST=localhost
DB_PORT=5432
```

Сгенерировать ключ (окружение должно быть активировано):

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Ключ вставляйте в `.env` в одинарных кавычках: в нём могут встречаться спецсимволы.

### 4. Поднять базу данных в Docker

Значения `POSTGRES_*` должны совпадать с `.env`:

```bash
docker run --name shkaf-postgres -e POSTGRES_USER=shkaf -e POSTGRES_PASSWORD=shkaf -e POSTGRES_DB=shkaf -p 5432:5432 -d postgis/postgis:16-3.5
```

При следующих запусках контейнер создавать заново не нужно:

```bash
docker start shkaf-postgres
```

Если порт 5432 занят, укажите другой, например `-p 5433:5432`, и пропишите его в `DB_PORT`.

### 5. Применить миграции

`manage.py` лежит в папке `shkaf`:

```bash
cd shkaf
```

```bash
python manage.py migrate
```

Для входа в админку создайте суперпользователя:

```bash
python manage.py createsuperuser
```

## Запуск

Из папки `shkaf` с активированным окружением:

```bash
python manage.py runserver
```

| Адрес | Что открывается |
|---|---|
| http://127.0.0.1:8000/api/v1/docs/ | Swagger UI |
| http://127.0.0.1:8000/api/v1/schema/ | Схема OpenAPI |
| http://127.0.0.1:8000/admin/ | Админка |

## Проверка кода

Тесты (из папки `shkaf`):

```bash
python manage.py test
```

Линтер:

```bash
ruff check .
```
