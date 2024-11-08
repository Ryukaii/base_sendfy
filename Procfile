web: gunicorn app:app --bind 0.0.0.0:8080
worker: celery -A celery_worker worker --loglevel=info
