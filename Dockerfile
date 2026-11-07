
# =========================================================
# BASE
# =========================================================
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/

# =========================================================
# DESENVOLVIMENTO LOCAL
# =========================================================
FROM base AS development

RUN pip install --upgrade pip \
    && pip install -r requirements/local.txt

COPY . .

# =========================================================
# TESTES E2E
# =========================================================
FROM development AS e2e

RUN playwright install --with-deps chromium

# =========================================================
# PRODUÇÃO - RENDER
# =========================================================
FROM base AS production

RUN pip install --upgrade pip \
    && pip install -r requirements/production.txt

COPY . .

ENV DJANGO_SETTINGS_MODULE=config.settings.production

EXPOSE 10000

CMD ["sh", "-c", "set -e; python manage.py migrate --noinput; python manage.py collectstatic --noinput; if [ \"${RUN_PRESERVA_PET_IMPORT:-false}\" = \"true\" ]; then python manage.py importar_catalogo_preserva_pet --tenant-slug preserva-pet --once; fi; exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000}"]
