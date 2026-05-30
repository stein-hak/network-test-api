# Network Test API Documentation

## Overview

Distributed network testing system with orchestrator-worker architecture for testing VLESS proxy connections across multiple geographic locations.

**Base URL**: `http://<orchestrator-host>:8000`

**Interactive Documentation**: `http://<orchestrator-host>:8000/docs`

---

## Architecture

- **Orchestrator**: Coordinates tests across multiple workers, manages job queue via Redis
- **Workers**: Execute actual network tests from different locations
- **Job Queue**: Redis-based async job management with 1-hour TTL

---

## API Endpoints

### 1. Check Worker IPs

Get the outbound IP addresses of all configured workers.

**Endpoint**: `GET /orchestrator/check-all-ips`

**Response**:
```json
{
  "workers": [
    {
      "worker_url": "http://192.168.2.10:8001",
      "ip": "203.0.113.10",
      "location": "Amsterdam, NL"
    },
    {
      "worker_url": "http://10.11.0.3:8005",
      "ip": "198.51.100.5",
      "location": "New York, US"
    }
  ]
}
```

---

### 2. Test VLESS Connection (Async)

Submit an async VLESS connection test to all workers.

**Endpoint**: `POST /orchestrator/test/vless/async`

**Request Body**:
```json
{
  "vless_url": "vless://uuid@example.com:443?type=tcp&security=reality&...",
  "timeout": 20,
  "test_url": "https://httpbin.org/get"
}
```

**Parameters**:
- `vless_url` (required): Full VLESS connection URL
- `timeout` (optional): Test timeout in seconds (default: 20)
- `test_url` (optional): URL to test connectivity (default: https://httpbin.org/get)

**Response**:
```json
{
  "job_id": "47a8650f-e5d8-4910-a930-27b1eb91b2d5",
  "status": "pending",
  "message": "Job submitted successfully"
}
```

---

### 3. Get Job Status & Results

Get job status with aggregated worker results (single polling endpoint).

**Endpoint**: `GET /orchestrator/job/{job_id}`

**Path Parameters**:
- `job_id`: UUID returned from job submission

**Response (Running)**:
```json
{
  "job_id": "47a8650f-e5d8-4910-a930-27b1eb91b2d5",
  "job_type": "vless_test",
  "status": "running",
  "progress": 50,
  "created_at": "2026-05-30T01:17:53.514338",
  "updated_at": "2026-05-30T01:17:55.000000",
  "total_workers": 4,
  "successful": 0,
  "failed": 0,
  "worker_results": [],
  "error": null
}
```

**Response (Completed)**:
```json
{
  "job_id": "47a8650f-e5d8-4910-a930-27b1eb91b2d5",
  "job_type": "vless_test",
  "status": "completed",
  "progress": 100,
  "created_at": "2026-05-30T01:17:53.514338",
  "updated_at": "2026-05-30T01:18:00.916709",
  "total_workers": 4,
  "successful": 2,
  "failed": 2,
  "worker_results": [
    {
      "worker_url": "http://192.168.2.10:8001",
      "worker_job_id": "47a8650f-e5d8-4910-a930-27b1eb91b2d5_0",
      "status": "completed",
      "test_result": {
        "success": true,
        "remark": "Amsterdam NL",
        "latency_ms": 245,
        "external_ip": "203.0.113.10",
        "ip_info": {
          "city": "Amsterdam",
          "country": "NL",
          "org": "AS16509 Amazon.com, Inc."
        }
      },
      "error": null
    },
    {
      "worker_url": "http://192.168.2.11:8001",
      "worker_job_id": "47a8650f-e5d8-4910-a930-27b1eb91b2d5_1",
      "status": "completed",
      "test_result": {
        "success": false,
        "remark": "London UK",
        "latency_ms": null,
        "error": "Connection timeout"
      },
      "error": null
    }
  ],
  "error": null
}
```

**Status Codes**:
- `200 OK`: Job found
- `404 Not Found`: Job not found or expired (1-hour TTL)

---

### 4. Test VLESS Connection (Synchronous)

Test VLESS connection synchronously (waits for all workers to complete).

**Endpoint**: `POST /orchestrator/test/vless`

**Request Body**: Same as async version

**Response**: Immediate results from all workers (may take 20+ seconds)

```json
{
  "total_workers": 4,
  "successful": 2,
  "results": [
    {
      "worker_url": "http://192.168.2.10:8001",
      "success": true,
      "test_result": { /* same as async */ }
    }
  ]
}
```

⚠️ **Note**: Synchronous endpoint may timeout for slow connections. Use async endpoint for production.

---

### 5. Test Subscription (Async)

Test VLESS subscription URL and optionally test individual links across all workers.

**Endpoint**: `POST /orchestrator/test/subscription/async`

**Request Body**:
```json
{
  "subscription_url": "https://example.com/sub/user123",
  "timeout": 30,
  "test_vless_links": true,
  "max_links_to_test": 3
}
```

**Parameters**:
- `subscription_url` (required): Subscription URL to test
- `timeout` (optional): Timeout in seconds (default: 30)
- `test_vless_links` (optional): Whether to test VLESS links via xray (default: false)
- `max_links_to_test` (optional): Maximum links to test (default: 3, 0 = all)

**How It Works**:
1. Orchestrator fetches and parses subscription **once**
2. Extracts VLESS links from subscription
3. Sends **same links** to all workers for testing
4. Each worker tests links via xray and reports results

**Response**:
```json
{
  "job_id": "uuid-here",
  "status": "pending",
  "message": "Job submitted successfully"
}
```

**Job Status Response** (via `/orchestrator/job/{job_id}`):
```json
{
  "job_id": "uuid-here",
  "job_type": "subscription_test",
  "status": "completed",
  "progress": 100,
  "total_workers": 4,
  "successful": 4,
  "failed": 0,
  "worker_results": [
    {
      "worker_url": "http://worker1:8001",
      "worker_job_id": "uuid-here_0",
      "status": "completed",
      "test_result": {
        "success": true,
        "accessible": true,
        "link_count": 14,
        "tested_links": [
          {
            "success": true,
            "remark": "Server A",
            "latency_ms": 245.5,
            "error": null
          },
          {
            "success": false,
            "remark": "Server B",
            "latency_ms": null,
            "error": "Connection timeout"
          }
        ],
        "error": null
      },
      "error": null
    }
  ]
}
```

**Key Feature**: All workers test the **same VLESS links**, enabling geographic comparison of link performance across different network providers.

---

### 6. Test Basic Connectivity

Test basic TCP/HTTP connectivity from all workers (no proxy).

**Endpoint**: `POST /orchestrator/test/connectivity`

**Request Body**:
```json
{
  "target": "example.com",
  "port": 443,
  "timeout": 10,
  "protocol": "https"
}
```

**Response**:
```json
{
  "total_workers": 4,
  "successful": 4,
  "results": [
    {
      "worker_url": "http://192.168.2.10:8001",
      "success": true,
      "latency_ms": 42,
      "accessible": true
    }
  ]
}
```

---

## Typical Workflow (Frontend)

### Async Job Pattern (Recommended)

```javascript
// 1. Submit test job
const response = await fetch('http://orchestrator:8000/orchestrator/test/vless/async', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    vless_url: 'vless://...',
    timeout: 20
  })
});
const {job_id} = await response.json();

// 2. Poll for results (single endpoint)
const pollInterval = setInterval(async () => {
  const job = await fetch(`http://orchestrator:8000/orchestrator/job/${job_id}`)
    .then(r => r.json());

  // Update UI with progress
  updateProgress(job.status, job.progress);

  // Check if completed
  if (job.status === 'completed') {
    clearInterval(pollInterval);

    // Display aggregated results
    displayResults({
      total: job.total_workers,
      successful: job.successful,
      failed: job.failed,
      details: job.worker_results
    });
  }

  if (job.status === 'failed') {
    clearInterval(pollInterval);
    showError(job.error);
  }
}, 2000); // Poll every 2 seconds
```

---

## Job States

| State | Description |
|-------|-------------|
| `pending` | Job created, waiting to start |
| `running` | Workers are executing tests |
| `completed` | All workers finished (check `successful` count) |
| `failed` | Job execution failed (see `error` field) |

---

## Worker Result Fields

| Field | Type | Description |
|-------|------|-------------|
| `worker_url` | string | Worker endpoint URL |
| `worker_job_id` | string | Sub-job UUID for this worker |
| `status` | string | Worker job status (completed/failed/unknown) |
| `test_result` | object | Test results (null if pending) |
| `test_result.success` | boolean | Whether test succeeded |
| `test_result.latency_ms` | number | Connection latency in milliseconds |
| `test_result.external_ip` | string | IP seen through proxy |
| `test_result.ip_info` | object | GeoIP information |
| `test_result.error` | string | Error message if failed |
| `error` | string | Worker-level error (if any) |

---

## Error Handling

### HTTP Status Codes

- `200 OK`: Request successful
- `404 Not Found`: Job not found or expired
- `422 Unprocessable Entity`: Invalid request parameters
- `500 Internal Server Error`: Server error

### Error Response Format

```json
{
  "detail": "Job not found or expired"
}
```

---

## Rate Limits & Quotas

- **Job TTL**: 1 hour (jobs auto-expire from Redis)
- **Concurrent Jobs**: No hard limit (Redis-based queue)
- **Request Timeout**: 120 seconds default
- **Worker Timeout**: Configurable per-request (default: 20s)

---

## Configuration

### Environment Variables (Orchestrator)

```bash
WORKERS=http://worker1:8001,http://worker2:8001,http://worker3:8001
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
PORT=8000
```

### Worker Configuration

Each worker runs independently:
```bash
ROLE=worker
PORT=8001
LOG_LEVEL=INFO
```

---

## Examples

### cURL Examples

**Submit async test**:
```bash
curl -X POST http://orchestrator:8000/orchestrator/test/vless/async \
  -H "Content-Type: application/json" \
  -d '{
    "vless_url": "vless://uuid@example.com:443?type=tcp&security=reality&...",
    "timeout": 20
  }'
```

**Get job results**:
```bash
curl http://orchestrator:8000/orchestrator/job/47a8650f-e5d8-4910-a930-27b1eb91b2d5
```

**Check worker IPs**:
```bash
curl http://orchestrator:8000/orchestrator/check-all-ips
```

### Python Example

```python
import requests
import time

# Submit test
response = requests.post(
    'http://orchestrator:8000/orchestrator/test/vless/async',
    json={
        'vless_url': 'vless://...',
        'timeout': 20
    }
)
job_id = response.json()['job_id']

# Poll for results
while True:
    job = requests.get(f'http://orchestrator:8000/orchestrator/job/{job_id}').json()

    print(f"Status: {job['status']} - Progress: {job['progress']}%")

    if job['status'] == 'completed':
        print(f"Success: {job['successful']}/{job['total_workers']}")
        for result in job['worker_results']:
            test = result.get('test_result', {})
            if test.get('success'):
                print(f"  ✓ {result['worker_url']}: {test['latency_ms']}ms")
            else:
                print(f"  ✗ {result['worker_url']}: {test.get('error')}")
        break

    time.sleep(2)
```

---

## Deployment

### Docker Compose

See `docker-compose.yml` for orchestrator + workers deployment.

### Systemd Services

Orchestrator and workers run as systemd services with automatic restart.

**Check status**:
```bash
systemctl status network-test-orchestrator
systemctl status network-test-worker-cable
```

---

## Monitoring

- **Logs**: `journalctl -u network-test-orchestrator -f`
- **Redis**: Monitor job queue with `redis-cli`
- **Health**: Check `/docs` endpoint availability

---

## Troubleshooting

### Job stuck in "running" state
- Check worker logs: `journalctl -u network-test-worker-* -n 100`
- Verify Redis connection
- Check network connectivity to workers

### Workers timing out
- Increase timeout in request body
- Check worker system load
- Verify xray installation on workers

### "Job not found or expired"
- Jobs expire after 1 hour
- Re-submit the test

---

## Scheduled Tests (Orchestrator)

### Overview

The orchestrator supports automated recurring tests via APScheduler integration. Scheduled tests:
- Run automatically on interval (hours) or cron schedule
- Execute via orchestrator async endpoints across all workers
- Store job results in Redis (1-hour TTL) and metadata in SQLite
- Can be enabled/disabled dynamically without deletion

### Architecture

**Dual Storage**:
- **SQLite**: Persistent schedule configuration, run history, last job_id
- **Redis**: Ephemeral job results (1-hour TTL, auto-cleanup)

**Workflow**:
1. Scheduler triggers at configured time
2. Creates job via `/orchestrator/test/{type}/async`
3. Stores job_id in SQLite `last_task_id` field
4. Job executes across all workers in background
5. Results available via Redis for 1 hour

### Create Scheduled Test

**Endpoints**:
- `POST /orchestrator/scheduled/vless`
- `POST /orchestrator/scheduled/subscription`
- `POST /orchestrator/scheduled/connectivity`
- `POST /orchestrator/scheduled/ssl`

**Request Body (Subscription Example)**:
```json
{
  "name": "Daily Subscription Check",
  "subscription_url": "https://example.com/sub/user123",
  "interval_hours": 24,
  "test_vless_links": true,
  "max_links_to_test": 3,
  "timeout": 30,
  "enabled": true
}
```

**Scheduling Options**:
- `interval_hours`: Run every N hours (e.g., 6 = every 6 hours)
- `cron_expression`: Cron format (e.g., "0 */6 * * *" = every 6 hours, "*/2 * * * *" = every 2 minutes)
- **Must provide either `interval_hours` OR `cron_expression`, not both**

**Response**:
```json
{
  "scheduled_id": "uuid-here",
  "name": "Daily Subscription Check",
  "task_type": "subscription",
  "schedule": "every 24 hours",
  "enabled": true,
  "message": "Scheduled subscription test created successfully"
}
```

### List Scheduled Tests

**Endpoint**: `GET /orchestrator/scheduled`

**Response**:
```json
{
  "count": 2,
  "scheduled_tests": [
    {
      "id": "uuid-1",
      "name": "Daily Subscription Check",
      "task_type": "subscription",
      "enabled": true,
      "schedule": "every 24h",
      "last_run": "2026-05-30T05:56:00.298314",
      "last_job_id": "job-uuid-123",
      "run_count": 42,
      "created_at": "2026-05-20T10:00:00"
    }
  ]
}
```

### Get Scheduled Test Details with Results

**Endpoint**: `GET /orchestrator/scheduled/{scheduled_id}`

Returns schedule configuration + latest job results from Redis (if available).

**Response**:
```json
{
  "id": "uuid-1",
  "name": "Daily Subscription Check",
  "task_type": "subscription",
  "enabled": true,
  "schedule": "every 24h",
  "request_data": {
    "subscription_url": "https://example.com/sub/user123",
    "timeout": 30,
    "test_vless_links": true,
    "max_links_to_test": 3
  },
  "last_run_at": "2026-05-30T05:56:00.298314",
  "last_job_id": "job-uuid-123",
  "run_count": 42,
  "created_at": "2026-05-20T10:00:00",
  "last_job_result": {
    "job_id": "job-uuid-123",
    "job_type": "subscription_test",
    "status": "completed",
    "progress": 100,
    "total_workers": 4,
    "successful": 4,
    "failed": 0,
    "worker_results": [
      {
        "worker_url": "http://worker1:8001",
        "status": "completed",
        "test_result": {
          "success": true,
          "link_count": 3,
          "tested_links": [...]
        }
      }
    ],
    "created_at": "2026-05-30T05:56:00.024640",
    "updated_at": "2026-05-30T05:56:15.123456"
  }
}
```

**Note**: `last_job_result` will be `null` if:
- Job hasn't run yet
- Job expired from Redis (>1 hour old)
- Job is still running

### Enable/Disable Scheduled Test

**Endpoint**: `PUT /orchestrator/scheduled/{scheduled_id}/enable?enabled=true`

**Query Parameters**:
- `enabled`: `true` to enable, `false` to disable

**Response**:
```json
{
  "message": "Scheduled test 'Daily Subscription Check' enabled",
  "scheduled_id": "uuid-1",
  "enabled": true
}
```

### Delete Scheduled Test

**Endpoint**: `DELETE /orchestrator/scheduled/{scheduled_id}`

Removes from both APScheduler and SQLite database.

**Response**:
```json
{
  "message": "Scheduled test 'Daily Subscription Check' deleted successfully",
  "scheduled_id": "uuid-1"
}
```

### Cron Expression Format

Standard cron format with 5 fields:
```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of week (0 - 6) (Sunday = 0)
│ │ │ │ │
│ │ │ │ │
* * * * *
```

**Examples**:
- `0 */6 * * *` - Every 6 hours at minute 0
- `*/2 * * * *` - Every 2 minutes
- `0 0 * * *` - Daily at midnight
- `0 9 * * 1` - Every Monday at 9:00 AM
- `*/15 * * * *` - Every 15 minutes

### Best Practices

1. **Job TTL**: Results expire after 1 hour in Redis. For long intervals, fetch results soon after execution
2. **Scheduling**: Use cron for specific times, interval for simple recurring tasks
3. **Monitoring**: Check `run_count` and `last_run_at` to verify scheduler is working
4. **Error Handling**: Check `last_job_result.status` - may be `failed` even if scheduled test succeeded
5. **Resource Usage**: Avoid too-frequent schedules (< 5 minutes) to prevent worker overload

---

## Support

- GitHub Issues: https://github.com/stein-hak/network-test-api/issues
- Interactive API Docs: http://orchestrator:8000/docs
