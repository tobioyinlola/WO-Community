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
RUN chown -R app:app /app
USER app

ENV DJANGO_SETTINGS_MODULE=config.settings.production
EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "30", "--graceful-timeout", "30", "--access-logfile", "-"]
