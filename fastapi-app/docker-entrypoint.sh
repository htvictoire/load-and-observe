#!/bin/bash
set -e

case "$1" in
  web)
    echo "Starting FastAPI web server..."
    exec uvicorn main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    echo "Starting Celery worker..."
    exec celery -A tasks worker --loglevel=info
    ;;
  beat)
    echo "Starting Celery beat scheduler..."
    exec celery -A tasks beat --loglevel=info
    ;;
  *)
    echo "Running custom command: $@"
    exec "$@"
    ;;
esac