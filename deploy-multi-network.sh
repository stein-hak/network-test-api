#!/bin/bash
set -e

echo "========================================="
echo "Multi-Network Test API Deployment"
echo "========================================="

# Stop any existing containers
echo "Stopping existing containers..."
docker compose -f docker-compose-multi-network.yml down 2>/dev/null || true

# Build images
echo "Building Docker images..."
docker compose -f docker-compose-multi-network.yml build

# Start all services
echo "Starting services..."
docker compose -f docker-compose-multi-network.yml up -d

# Wait for services to start
echo "Waiting for services to start..."
sleep 10

# Check service status
echo ""
echo "========================================="
echo "Service Status"
echo "========================================="
docker compose -f docker-compose-multi-network.yml ps

echo ""
echo "========================================="
echo "Testing Worker IPs"
echo "========================================="

# Test each worker individually
for port in 8001 8002 8003 8004; do
    echo ""
    echo "Testing worker on port $port..."
    curl -s http://127.0.0.1:$port/myip 2>/dev/null | jq '.' || echo "Worker on port $port not responding"
done

echo ""
echo "========================================="
echo "Testing Orchestrator"
echo "========================================="
echo ""
echo "Orchestrator aggregated IP check:"
curl -s http://127.0.0.1:8000/orchestrator/check-all-ips 2>/dev/null | jq '.' || echo "Orchestrator not responding"

echo ""
echo "========================================="
echo "Deployment Complete!"
echo "========================================="
echo "Orchestrator: http://localhost:8000"
echo "Worker 1 (Ethernet): http://localhost:8001"
echo "Worker 2 (Tele2): http://localhost:8002"
echo "Worker 3 (MTS): http://localhost:8003"
echo "Worker 4 (USB): http://localhost:8004"
echo ""
echo "Test IP verification: curl http://localhost:8000/orchestrator/check-all-ips | jq"
echo "========================================="
