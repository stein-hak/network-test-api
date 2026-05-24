#!/usr/bin/env python3
"""
Network Test API - REST API for testing connectivity, SSL, and VLESS links
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, List
import logging
from datetime import datetime

from app.testers.connectivity import ConnectivityTester
from app.testers.ssl_checker import SSLChecker
from app.testers.vless_tester import VLESSTester
from app.testers.subscription import SubscriptionTester

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Network Test API",
    description="REST API for testing domain/IP connectivity, SSL certificates, VLESS links, and subscriptions",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class ConnectivityTestRequest(BaseModel):
    target: str = Field(..., description="Domain or IP address to test")
    port: int = Field(443, description="Port to test (default: 443)")
    timeout: int = Field(10, description="Timeout in seconds (default: 10)")
    protocol: str = Field("tcp", description="Protocol: tcp, udp, http, https")

    @validator('timeout')
    def validate_timeout(cls, v):
        if v < 1 or v > 60:
            raise ValueError('Timeout must be between 1 and 60 seconds')
        return v

class SSLTestRequest(BaseModel):
    domain: str = Field(..., description="Domain to check SSL certificate")
    port: int = Field(443, description="Port (default: 443)")
    timeout: int = Field(10, description="Timeout in seconds")
    verify_chain: bool = Field(True, description="Verify certificate chain")

class VLESSTestRequest(BaseModel):
    vless_url: str = Field(..., description="VLESS URL to test")
    timeout: int = Field(15, description="Timeout in seconds (default: 15)")
    test_url: str = Field("https://httpbin.org/get", description="URL to test through proxy")

class SubscriptionTestRequest(BaseModel):
    subscription_url: str = Field(..., description="Subscription URL to test")
    timeout: int = Field(10, description="Timeout in seconds")
    test_vless_links: bool = Field(False, description="Also test VLESS links in subscription")
    max_links_to_test: int = Field(3, description="Max VLESS links to test (if test_vless_links=true)")

class BatchTestRequest(BaseModel):
    targets: List[str] = Field(..., description="List of domains/IPs/VLESS URLs to test")
    test_type: str = Field(..., description="Type: connectivity, ssl, vless")
    timeout: int = Field(10, description="Timeout per test")

# Response models
class ConnectivityTestResponse(BaseModel):
    success: bool
    target: str
    port: int
    protocol: str
    latency_ms: Optional[float]
    error: Optional[str]
    timestamp: str

class SSLTestResponse(BaseModel):
    success: bool
    domain: str
    valid: bool
    issuer: Optional[str]
    subject: Optional[str]
    expires: Optional[str]
    days_until_expiry: Optional[int]
    error: Optional[str]
    timestamp: str

class VLESSTestResponse(BaseModel):
    success: bool
    remark: str
    latency_ms: Optional[float]
    error: Optional[str]
    timestamp: str

class SubscriptionTestResponse(BaseModel):
    success: bool
    subscription_url: str
    accessible: bool
    link_count: Optional[int]
    tested_links: Optional[List[VLESSTestResponse]]
    error: Optional[str]
    timestamp: str

# Endpoints
@app.get("/")
async def root():
    """API root - health check"""
    return {
        "service": "Network Test API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "connectivity": "/test/connectivity",
            "ssl": "/test/ssl",
            "vless": "/test/vless",
            "subscription": "/test/subscription",
            "batch": "/test/batch"
        }
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.post("/test/connectivity", response_model=ConnectivityTestResponse)
async def test_connectivity(request: ConnectivityTestRequest):
    """
    Test connectivity to a domain or IP address

    - Supports TCP, UDP, HTTP, HTTPS protocols
    - Returns latency measurement
    - Configurable timeout
    """
    logger.info(f"Testing connectivity to {request.target}:{request.port} ({request.protocol})")

    tester = ConnectivityTester()
    result = tester.test(
        target=request.target,
        port=request.port,
        timeout=request.timeout,
        protocol=request.protocol
    )

    return ConnectivityTestResponse(
        success=result["success"],
        target=request.target,
        port=request.port,
        protocol=request.protocol,
        latency_ms=result.get("latency_ms"),
        error=result.get("error"),
        timestamp=datetime.utcnow().isoformat()
    )

@app.post("/test/ssl", response_model=SSLTestResponse)
async def test_ssl(request: SSLTestRequest):
    """
    Test SSL certificate for a domain

    - Verifies certificate validity
    - Checks expiration date
    - Validates certificate chain
    - Returns issuer and subject information
    """
    logger.info(f"Testing SSL certificate for {request.domain}:{request.port}")

    checker = SSLChecker()
    result = checker.check(
        domain=request.domain,
        port=request.port,
        timeout=request.timeout,
        verify_chain=request.verify_chain
    )

    return SSLTestResponse(
        success=result["success"],
        domain=request.domain,
        valid=result.get("valid", False),
        issuer=result.get("issuer"),
        subject=result.get("subject"),
        expires=result.get("expires"),
        days_until_expiry=result.get("days_until_expiry"),
        error=result.get("error"),
        timestamp=datetime.utcnow().isoformat()
    )

@app.post("/test/vless", response_model=VLESSTestResponse)
async def test_vless(request: VLESSTestRequest):
    """
    Test VLESS connection link

    - Parses VLESS URL
    - Starts temporary Xray instance
    - Tests connectivity through proxy
    - Measures latency
    - Supports Reality, gRPC, WebSocket, XHTTP
    """
    logger.info(f"Testing VLESS connection")

    tester = VLESSTester()
    result = tester.test(
        vless_url=request.vless_url,
        timeout=request.timeout,
        test_url=request.test_url
    )

    return VLESSTestResponse(
        success=result["success"],
        remark=result.get("remark", "Unknown"),
        latency_ms=result.get("latency_ms"),
        error=result.get("error"),
        timestamp=datetime.utcnow().isoformat()
    )

@app.post("/test/subscription", response_model=SubscriptionTestResponse)
async def test_subscription(request: SubscriptionTestRequest):
    """
    Test subscription URL

    - Checks URL accessibility
    - Parses subscription content
    - Counts VLESS links
    - Optionally tests individual links
    """
    logger.info(f"Testing subscription URL: {request.subscription_url}")

    tester = SubscriptionTester()
    result = tester.test(
        subscription_url=request.subscription_url,
        timeout=request.timeout,
        test_links=request.test_vless_links,
        max_links=request.max_links_to_test
    )

    tested_links = None
    if result.get("tested_links"):
        tested_links = [
            VLESSTestResponse(
                success=link["success"],
                remark=link.get("remark", "Unknown"),
                latency_ms=link.get("latency_ms"),
                error=link.get("error"),
                timestamp=datetime.utcnow().isoformat()
            )
            for link in result["tested_links"]
        ]

    return SubscriptionTestResponse(
        success=result["success"],
        subscription_url=request.subscription_url,
        accessible=result.get("accessible", False),
        link_count=result.get("link_count"),
        tested_links=tested_links,
        error=result.get("error"),
        timestamp=datetime.utcnow().isoformat()
    )

@app.post("/test/batch")
async def test_batch(request: BatchTestRequest, background_tasks: BackgroundTasks):
    """
    Batch test multiple targets

    - Tests multiple targets in parallel
    - Supports connectivity, SSL, and VLESS tests
    - Returns aggregated results
    """
    logger.info(f"Batch testing {len(request.targets)} targets ({request.test_type})")

    results = []

    if request.test_type == "connectivity":
        tester = ConnectivityTester()
        for target in request.targets:
            # Parse port if included (e.g., "example.com:443")
            if ":" in target and not target.startswith("["):
                domain, port = target.rsplit(":", 1)
                port = int(port)
            else:
                domain = target
                port = 443

            result = tester.test(domain, port, request.timeout, "tcp")
            results.append({
                "target": target,
                "success": result["success"],
                "latency_ms": result.get("latency_ms"),
                "error": result.get("error")
            })

    elif request.test_type == "ssl":
        checker = SSLChecker()
        for target in request.targets:
            if ":" in target:
                domain, port = target.rsplit(":", 1)
                port = int(port)
            else:
                domain = target
                port = 443

            result = checker.check(domain, port, request.timeout)
            results.append({
                "target": target,
                "success": result["success"],
                "valid": result.get("valid"),
                "days_until_expiry": result.get("days_until_expiry"),
                "error": result.get("error")
            })

    elif request.test_type == "vless":
        tester = VLESSTester()
        for vless_url in request.targets:
            result = tester.test(vless_url, request.timeout)
            results.append({
                "vless_url": vless_url[:50] + "...",
                "remark": result.get("remark"),
                "success": result["success"],
                "latency_ms": result.get("latency_ms"),
                "error": result.get("error")
            })

    else:
        raise HTTPException(status_code=400, detail="Invalid test_type. Must be: connectivity, ssl, or vless")

    return {
        "test_type": request.test_type,
        "total": len(request.targets),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "results": results,
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
