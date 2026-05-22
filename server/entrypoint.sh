#!/bin/bash
set -e

echo "Generating gRPC code from proto..."
python -m grpc_tools.protoc \
    -I/app/proto \
    --python_out=/app/server \
    --grpc_python_out=/app/server \
    /app/proto/booking.proto

echo "Waiting for PostgreSQL..."
until pg_isready -h ${POSTGRES_HOST:-postgres} -p ${POSTGRES_PORT:-5432} -U ${POSTGRES_USER:-qa}; do
  sleep 1
done

echo "Running migrations..."
PGPASSWORD=${POSTGRES_PASSWORD:-qa123} psql -h ${POSTGRES_HOST:-postgres} -U ${POSTGRES_USER:-qa} -d ${POSTGRES_DB:-bookings} -f /app/migrations/init.sql

echo "Starting gRPC server..."
cd /app/server
python server.py
