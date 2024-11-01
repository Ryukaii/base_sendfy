#!/bin/bash

echo "Starting SMS Platform services..."

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to check Redis connection
check_redis() {
    local max_attempts=$1
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if redis-cli ping &>/dev/null; then
            return 0
        fi
        attempt=$((attempt + 1))
        log "Checking Redis connection... (attempt $attempt/$max_attempts)"
        sleep 2
    done
    return 1
}

# Start Redis server
log "Starting Redis server..."
redis-server --daemonize yes &>/dev/null

# Wait for Redis to be ready
log "Waiting for Redis to be ready..."
if check_redis 30; then
    log "Redis is ready and accepting connections!"
else
    log "Error: Redis failed to start"
    exit 1
fi

# Start Celery worker
log "Starting Celery worker..."
celery -A celery_worker worker --loglevel=info &
CELERY_PID=$!

# Monitor function
monitor_services() {
    while true; do
        if ! redis-cli ping &>/dev/null; then
            log "Error: Redis connection lost"
            exit 1
        fi
        
        if ! ps -p $CELERY_PID > /dev/null; then
            log "Error: Celery worker died"
            exit 1
        fi
        sleep 5
    done
}

# Start monitoring in background
monitor_services &
MONITOR_PID=$!

# Set up environment
export FLASK_APP=app.py
export FLASK_ENV=development
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Start Flask application
log "Starting Flask application..."
python app.py
