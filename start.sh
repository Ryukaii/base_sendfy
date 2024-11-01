#!/bin/bash
# Start Redis server
redis-server --daemonize yes

# Start Celery worker
celery -A celery_worker worker --loglevel=info &

# Start Flask application
python main.py
