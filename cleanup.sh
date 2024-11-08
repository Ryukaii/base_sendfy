#!/bin/bash
echo "Cleaning up services..."
pkill -f 'celery worker' || true
pkill redis-server || true
rm -f celery.pid
sleep 2
