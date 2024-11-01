#!/bin/bash

echo "Starting SMS Platform services..."

# Start Redis server
echo "Starting Redis server..."
if ! redis-server --daemonize yes; then
    echo "Error: Failed to start Redis server"
    exit 1
fi

# Wait for Redis to be ready with timeout and health check
echo "Waiting for Redis to be ready..."
max_attempts=30
attempt=0
while ! redis-cli ping &>/dev/null; do
    if [ $attempt -ge $max_attempts ]; then
        echo "Error: Redis server failed to respond within timeout"
        exit 1
    fi
    echo "Waiting for Redis... (attempt $((attempt + 1))/$max_attempts)"
    sleep 1
    ((attempt++))
done
echo "Redis is ready!"

# Start Celery worker with proper logging
echo "Starting Celery worker..."
celery -A celery_worker worker --loglevel=info &
CELERY_PID=$!

# Wait for Celery to initialize with health check
echo "Waiting for Celery worker to initialize..."
max_attempts=30
attempt=0
while ! celery -A celery_worker inspect ping &>/dev/null; do
    if [ $attempt -ge $max_attempts ]; then
        echo "Error: Celery worker failed to initialize within timeout"
        exit 1
    fi
    if ! ps -p $CELERY_PID > /dev/null; then
        echo "Error: Celery worker process died"
        exit 1
    fi
    echo "Waiting for Celery... (attempt $((attempt + 1))/$max_attempts)"
    sleep 1
    ((attempt++))
done
echo "Celery worker is ready!"

# Health check function
health_check() {
    local service=$1
    local pid=$2
    
    if ! ps -p $pid > /dev/null; then
        echo "Error: $service process died unexpectedly"
        exit 1
    fi
}

# Start Flask application with proper template directory resolution
echo "Starting Flask application..."
export FLASK_APP=app.py
export FLASK_ENV=development
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Monitor services
(while true; do
    health_check "Redis" $(pgrep redis-server)
    health_check "Celery" $CELERY_PID
    sleep 30
done) &

# Start Flask application
exec python app.py
