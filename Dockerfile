FROM python:3.14-slim

# Системные библиотеки для GeoDjango
RUN apt-get update \
    && apt-get install -y --no-install-recommends binutils gdal-bin libproj-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH=/opt/venv/bin:$PATH
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock README.md .python-version ./
RUN uv sync --frozen --no-install-project

WORKDIR /app/shkaf
