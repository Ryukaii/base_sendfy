#!/bin/bash

# Exit on error and enable error tracing
set -e
set -x

# Function to log errors
log_error() {
    echo "ERROR: $1" >&2
}

# Check required environment variables
check_env() {
    if [ -z "${SMSDEV_API_KEY}" ]; then
        log_error "SMSDEV_API_KEY environment variable is not set"
        exit 1
    fi
}

# Create required directories with proper permissions
setup_directories() {
    echo "Setting up directories..."
    mkdir -p data "${HOME}/.redis" || { log_error "Failed to create directories"; exit 1; }
    chmod -R 755 data "${HOME}/.redis" || { log_error "Failed to set directory permissions"; exit 1; }
}

# Initialize data files if they don't exist
init_data_files() {
    echo "Initializing data files..."
    for file in integrations.json campaigns.json transactions.json sms_history.json scheduled_sms.json; do
        if [ ! -f "data/$file" ]; then
            echo "[]" > "data/$file" || { log_error "Failed to create $file"; exit 1; }
            chmod 644 "data/$file" || { log_error "Failed to set permissions for $file"; exit 1; }
            echo "Initialized data/$file"
        fi
    done
}

# Redis configuration with improved settings
setup_redis() {
    REDIS_CONFIG="${HOME}/.redis/redis.conf"
    cat > ${REDIS_CONFIG} << EOL
port 6379
bind 127.0.0.1
timeout 300
tcp-keepalive 60
maxmemory 256mb
maxmemory-policy allkeys-lru
appendonly yes
appendfsync everysec
dir ${HOME}/.redis
save 900 1
save 300 10
save 60 10000
loglevel notice
logfile ${HOME}/.redis/redis.log
pidfile ${HOME}/.redis/redis.pid
databases 16
EOL
}

# Main execution function
main() {
    echo "Starting SMS Platform services..."

    # Check and set up environment
    check_env
    setup_directories
    init_data_files

    # Export all required environment variables
    export SMSDEV_API_KEY="${SMSDEV_API_KEY}"
    export FLASK_ENV="production"
    export FLASK_APP="app.py"
    export REDIS_URL="redis://localhost:6379/0"
    export GUNICORN_CMD_ARGS="--access-logfile - --error-logfile - --capture-output --enable-stdio-inheritance"

    # Cleanup existing processes
    echo "Cleaning up existing processes..."
    pkill -f "redis-server" || true
    pkill -f "celery" || true
    pkill -f "gunicorn" || true
    sleep 2

    # Configure and start Redis
    setup_redis
    echo "Starting Redis server..."
    redis-server ${HOME}/.redis/redis.conf &

    # Wait for Redis with improved error handling
    echo "Waiting for Redis..."
    max_attempts=30
    attempt=1
    while [ $attempt -le $max_attempts ]; do
        if redis-cli ping &>/dev/null; then
            echo "Redis is ready"
            break
        fi
        if [ $attempt -eq $max_attempts ]; then
            echo "Error: Redis failed to start after $max_attempts attempts"
            exit 1
        fi
        echo "Attempt $attempt/$max_attempts: Waiting for Redis..."
        sleep 1
        attempt=$((attempt + 1))
    done

    # Start Celery worker with improved settings
    echo "Starting Celery worker..."
    celery -A celery_worker worker \
        --loglevel=info \
        --concurrency=2 \
        --max-tasks-per-child=100 \
        --max-memory-per-child=256000 \
        --task-events \
        --without-heartbeat \
        --pool=prefork \
        &

    # Wait for Celery worker
    echo "Waiting for Celery worker..."
    sleep 5

    # Start Flask application with improved gunicorn settings
    echo "Starting Flask application..."
    exec gunicorn \
        --bind 0.0.0.0:8080 \
        --worker-class gevent \
        --workers 1 \
        --threads 4 \
        --timeout 120 \
        --graceful-timeout 60 \
        --max-requests 1000 \
        --max-requests-jitter 50 \
        --backlog 2048 \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        --capture-output \
        --enable-stdio-inheritance \
        app:app
}

# Run the main function
main
