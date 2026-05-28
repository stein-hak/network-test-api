#!/bin/bash
set -e

# Default values
PORT=${PORT:-8000}
BIND_IP=${BIND_IP:-0.0.0.0}
ROLE=${ROLE:-worker}

echo "Starting network-test-api"
echo "  Role: $ROLE"
echo "  Bind IP: $BIND_IP"
echo "  Port: $PORT"
echo "  Network: ${NETWORK_NAME:-default}"

# Start uvicorn with the specified bind IP and port
exec uvicorn app.main:app --host "$BIND_IP" --port "$PORT"
