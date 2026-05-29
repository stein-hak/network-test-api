# Network Test API - Deployment Guide

## Quick Start

### 1. Clone with submodules
```bash
git clone --recurse-submodules <repo-url>
cd network-test-api
```

Or if already cloned:
```bash
git submodule update --init --recursive
```

### 2. Deploy with Docker Compose
```bash
docker compose up -d --build
```

The API will be available at `http://localhost:8000`

## Configuration

### Environment Variables
- `LOG_LEVEL`: Logging level (default: INFO)
- `DATABASE_URL`: SQLite database path (default: sqlite:////data/test_tasks.db)

### Volumes
- `./vless-tester`: Mounted as `/app/vless-tester` (vless testing library)
- `./data`: Persistent storage for SQLite database

## API Endpoints

### Sync Tests (immediate response)
- `POST /test/subscription` - Test subscription URL
- `POST /test/vless` - Test VLESS link
- `POST /test/ssl` - Check SSL certificate
- `POST /test/connectivity` - Test connectivity

### Async Tasks (submit and poll)
- `POST /test/subscription/async` - Submit async test (returns task_id)
- `GET /tasks/{task_id}` - Get task status and results
- `GET /tasks?status=completed&limit=50` - List tasks

### Scheduled Tests (periodic)
- `POST /scheduled/subscription` - Create scheduled test
- `GET /scheduled` - List scheduled tests
- `GET /scheduler/status` - Scheduler status

## Examples

### Async subscription test
```bash
# Submit task
curl -X POST http://localhost:8000/test/subscription/async \
  -H "Content-Type: application/json" \
  -d '{
    "subscription_url": "https://example.com/sub/user",
    "test_vless_links": true,
    "max_links_to_test": 0
  }'

# Returns: {"task_id": "uuid", "status": "pending"}

# Poll for results
curl http://localhost:8000/tasks/{task_id}
```

### Scheduled test (every 6 hours)
```bash
curl -X POST "http://localhost:8000/scheduled/subscription" \
  -d "name=Daily Subscription Test" \
  -d "subscription_url=https://example.com/sub/user" \
  -d "interval_hours=6" \
  -d "test_vless_links=true" \
  -d "max_links_to_test=0"
```

## Database

SQLite database is stored in `./data/test_tasks.db`
- Persists across container restarts
- Contains task history and scheduled test configurations

## Troubleshooting

### DNS issues during build
If Docker can't resolve registry-1.docker.io:
```bash
# Check DNS
cat /etc/resolv.conf

# Restart systemd-resolved
sudo systemctl restart systemd-resolved
```

### View logs
```bash
docker compose logs -f network-test-api
```

### Rebuild after code changes
```bash
docker compose down
docker compose up -d --build
```
