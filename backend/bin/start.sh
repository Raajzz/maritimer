#!/bin/sh
# Production start (Render free tier has no pre-deploy hook, so migrations run here; they are idempotent).
set -e
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  python manage.py migrate --noinput
  python manage.py seed_masterdata
fi
if [ -n "${BOOTSTRAP_ADMIN_EMAIL:-}" ]; then
  python manage.py bootstrap_admin --email "$BOOTSTRAP_ADMIN_EMAIL"
fi
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --timeout 60 --access-logfile -
