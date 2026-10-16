"""Gunicorn settings for production (picked up automatically from the working directory)."""

import os

# Render (and most PaaS hosts) tell the app which port to listen on.
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# The metro graph is loaded once per worker at import time and is read-only
# afterwards, so a couple of workers with a few threads each is plenty.
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 60

# Log requests and errors to stdout/stderr so they appear in the host's log viewer.
accesslog = "-"
errorlog = "-"
