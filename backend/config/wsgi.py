import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_wsgi_application()

from config import telemetry  # noqa: E402

telemetry.setup("wo-community-api")
