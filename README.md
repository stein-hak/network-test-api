# Network Test API

REST API for testing domain/IP connectivity, SSL certificates, VLESS proxy links, and subscription URLs.

## Features

- **Connectivity Testing**: Test TCP/UDP/HTTP/HTTPS connectivity with latency measurement
- **SSL Certificate Verification**: Check certificate validity, expiration dates, and chains
- **VLESS Link Testing**: Test VLESS proxy connections (Reality, gRPC, WebSocket, XHTTP)
- **Subscription Testing**: Verify subscription URLs and optionally test contained links
- **Batch Testing**: Test multiple targets in parallel

## Quick Start

### Clone with Submodules

```bash
git clone --recursive https://github.com/stein-hak/network-test-api.git
cd network-test-api
```

Or if already cloned:

```bash
git submodule update --init --recursive
```

### Using Docker (Recommended)

```bash
docker-compose up -d
```

API will be available at `http://localhost:8000`

### Manual Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install Xray (required for VLESS testing)
bash vless-tester/install-xray.sh

# Run the API
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API Documentation

Once running:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

### 1. Test Connectivity

```bash
curl -X POST http://localhost:8000/test/connectivity \
  -H "Content-Type: application/json" \
  -d '{
    "target": "google.com",
    "port": 443,
    "protocol": "tcp",
    "timeout": 10
  }'
```

**Response:**
```json
{
  "success": true,
  "target": "google.com",
  "port": 443,
  "protocol": "tcp",
  "latency_ms": 23.45,
  "error": null,
  "timestamp": "2024-05-24T10:30:00Z"
}
```

### 2. Test SSL Certificate

```bash
curl -X POST http://localhost:8000/test/ssl \
  -H "Content-Type: application/json" \
  -d '{
    "domain": "google.com",
    "port": 443,
    "timeout": 10
  }'
```

**Response:**
```json
{
  "success": true,
  "domain": "google.com",
  "valid": true,
  "issuer": "GTS CA 1C3",
  "subject": "*.google.com",
  "expires": "2024-08-20T12:00:00Z",
  "days_until_expiry": 88,
  "error": null,
  "timestamp": "2024-05-24T10:30:00Z"
}
```

### 3. Test VLESS Link

```bash
curl -X POST http://localhost:8000/test/vless \
  -H "Content-Type: application/json" \
  -d '{
    "vless_url": "vless://uuid@server:port?type=grpc&security=reality&pbk=xxx&sni=google.com#remark",
    "timeout": 15
  }'
```

**Response:**
```json
{
  "success": true,
  "remark": "node-germ0-gRPC",
  "latency_ms": 123.45,
  "error": null,
  "timestamp": "2024-05-24T10:30:00Z"
}
```

### 4. Test Subscription

```bash
curl -X POST http://localhost:8000/test/subscription \
  -H "Content-Type: application/json" \
  -d '{
    "subscription_url": "https://example.com/sub/email",
    "timeout": 10,
    "test_vless_links": true,
    "max_links_to_test": 3
  }'
```

**Response:**
```json
{
  "success": true,
  "subscription_url": "https://example.com/sub/email",
  "accessible": true,
  "link_count": 16,
  "tested_links": [
    {
      "success": true,
      "remark": "node-1",
      "latency_ms": 45.2,
      "error": null
    }
  ],
  "error": null,
  "timestamp": "2024-05-24T10:30:00Z"
}
```

### 5. Batch Test

```bash
curl -X POST http://localhost:8000/test/batch \
  -H "Content-Type: application/json" \
  -d '{
    "targets": ["google.com:443", "github.com:443", "cloudflare.com:443"],
    "test_type": "ssl",
    "timeout": 10
  }'
```

**Test types**: `connectivity`, `ssl`, `vless`

## Use Cases

### Monitor VPN Node Availability

```bash
curl -X POST http://localhost:8000/test/batch \
  -H "Content-Type: application/json" \
  -d '{
    "targets": [
      "node1.domain.com:443",
      "node2.domain.com:443"
    ],
    "test_type": "connectivity"
  }'
```

### Check SSL Expiration

```bash
curl -X POST http://localhost:8000/test/ssl \
  -H "Content-Type: application/json" \
  -d '{"domain": "your-domain.com"}'
```

### Verify VLESS Configuration

```bash
curl -X POST http://localhost:8000/test/vless \
  -H "Content-Type: application/json" \
  -d '{"vless_url": "vless://..."}'
```

## Integration Examples

### Python

```python
import requests

result = requests.post(
    "http://localhost:8000/test/connectivity",
    json={"target": "google.com", "port": 443, "protocol": "https"}
).json()

print(f"Success: {result['success']}, Latency: {result['latency_ms']}ms")
```

### Monitoring with Prometheus

```python
from prometheus_client import Gauge
import requests

node_up = Gauge('node_up', 'Node availability', ['node'])

def check_node(node):
    result = requests.post(
        "http://localhost:8000/test/connectivity",
        json={"target": node, "port": 443}
    ).json()

    node_up.labels(node=node).set(1 if result['success'] else 0)
```

## Architecture

```
network-test-api/
├── app/
│   ├── main.py                 # FastAPI application
│   ├── testers/
│   │   ├── connectivity.py     # TCP/UDP/HTTP testing
│   │   ├── ssl_checker.py      # SSL verification
│   │   ├── vless_tester.py     # VLESS link testing
│   │   └── subscription.py     # Subscription testing
├── vless-tester/               # Git submodule
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Requirements

- Python 3.11+
- Xray binary (automatically installed in Docker)
- [vless-tester](https://github.com/stein-hak/vless-tester) (included as submodule)

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest tests/
```

## License

MIT

## Credits

- [vless-tester](https://github.com/stein-hak/vless-tester) - VLESS connection testing
- [Xray-core](https://github.com/XTLS/Xray-core) - Proxy protocol support
