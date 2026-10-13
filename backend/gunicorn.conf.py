"""Gunicorn settings. The platform sets PORT; everything else can be tuned with variables."""

import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", min(multiprocessing.cpu_count() * 2 + 1, 4)))
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
graceful_timeout = 30
keepalive = 5
# Workers restart now and then so a slow leak cannot grow without limit.
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
# Logs from the platform's proxy carry the real address; trust its forwarded headers.
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "*")
