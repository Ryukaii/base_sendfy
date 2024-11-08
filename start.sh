#!/bin/bash

echo "Starting SMS Platform services..."

# Run cleanup script first
./cleanup.sh

# Create necessary directories
mkdir -p logs data

# Start Redis server with production configuration
echo "Starting Redis server..."
redis-server --daemonize yes \
    --port 6379 \
    --loglevel notice \
    --logfile logs/redis.log \
    --maxmemory 100mb \
    --maxmemory-policy allkeys-lru \
    --save 900 1 \
    --save 300 10 \
    --save 60 10000

# Wait for Redis to be ready with increased timeout
echo "Waiting for Redis to be ready..."
timeout 60 bash -c 'until redis-cli -p 6379 ping &>/dev/null; do sleep 1; done' || {
    echo "Error: Redis server failed to respond within timeout"
    exit 1
}

# Start Celery worker with improved configuration
echo "Starting Celery worker..."
celery -A celery_worker worker \
    --loglevel=INFO \
    --logfile=logs/celery.log \
    --pidfile=celery.pid \
    --max-tasks-per-child=1000 \
    --concurrency=2 \
    --detach

# Wait for Celery to start
echo "Waiting for Celery worker to initialize..."
sleep 10

# Check if Celery worker is running
if ! pgrep -f "celery worker" > /dev/null; then
    echo "Error: Failed to start Celery worker"
    cat logs/celery.log
    exit 1
fi

echo "Celery worker started successfully"

# Ensure the SMS API key is configured
if [ -z "${SMSDEV_API_KEY}" ]; then
    echo "Error: SMSDEV_API_KEY environment variable is not set"
    exit 1
fi

# Initialize admin user if needed
python3 init_admin.py

# Start Flask application with gunicorn
echo "Starting Flask application with gunicorn..."
exec gunicorn \
    --bind 0.0.0.0:80 \
    --workers 4 \
    --threads 2 \
    --timeout 120 \
    --worker-class gthread \
    --worker-tmp-dir /dev/shm \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log \
    --log-level info \
    --capture-output \
    --enable-stdio-inheritance \
    app:app
