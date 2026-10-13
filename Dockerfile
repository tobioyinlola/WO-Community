FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app
COPY pyproject.toml ./
# pip bundles its own copies of urllib3, msgpack and setuptools, which image scanners report and
# which no project pin can change. Nothing needs pip once the dependencies are installed.
RUN pip install --upgrade pip && pip install . && pip uninstall -y pip

COPY . .
# Static files are collected once, here, so the running container only reads them. The values are
# placeholders that the build needs to load settings; nothing from them is kept.
RUN DJANGO_SETTINGS_MODULE=config.settings.base SECRET_KEY=build-only     DATABASE_URL=postgres://build:build@localhost:5432/build     python manage.py collectstatic --noinput
RUN chown -R app:app /app
USER app

ENV DJANGO_SETTINGS_MODULE=config.settings.production
EXPOSE 8000

# The web process. The worker and scheduler run from the same image with their own command
# (see docs/deployment/railway.md).
CMD ["gunicorn", "config.wsgi:application", "-c", "gunicorn.conf.py"]
