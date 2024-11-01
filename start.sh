#!/bin/bash

echo "Starting SMS Platform services..."

# Start Redis server
echo "Starting Redis server..."
if ! redis-server --daemonize yes; then
    echo "Error: Failed to start Redis server"
    exit 1
fi

# Wait for Redis to be ready
echo "Waiting for Redis to be ready..."
timeout 30 bash -c 'until redis-cli ping &>/dev/null; do sleep 1; done' || {
    echo "Error: Redis server failed to respond within timeout"
    exit 1
}

# Start Celery worker
echo "Starting Celery worker..."
celery -A celery_worker worker --loglevel=info &
CELERY_PID=$!

# Wait for Celery to start
echo "Waiting for Celery worker to initialize..."
sleep 5

# Check if Celery is running
if ! ps -p $CELERY_PID > /dev/null; then
    echo "Error: Failed to start Celery worker"
    exit 1
fi

# Start Flask application
echo "Starting Flask application..."
exec python app.py
