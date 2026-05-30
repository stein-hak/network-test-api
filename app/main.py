#!/usr/bin/env python3
"""
Network Test API - REST API for testing connectivity, SSL, and VLESS links
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, List
import logging
from datetime import datetime
import threading
import os
import asyncio
import httpx
import requests as requests_lib
from requests.adapters import HTTPAdapter
from urllib3.util.connection import create_connection

from app.testers.connectivity import ConnectivityTester
from app.testers.ssl_checker import SSLChecker
from app.testers.vless_tester import VLESSTester
from app.testers.subscription import SubscriptionTester
from app.database import get_db, TestTask, ScheduledTest
from app.tasks import create_task, get_task, execute_task
from app.scheduler import init_scheduler, create_scheduled_test, get_scheduler_status, shutdown_scheduler
from app.job_manager import get_job_manager
from sqlalchemy.orm import Session

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Custom HTTPAdapter to bind to specific source IP
class SourceAddressAdapter(HTTPAdapter):
    def __init__(self, source_address, **kwargs):
        self.source_address = source_address
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["source_address"] = (self.source_address, 0)
        return super().init_poolmanager(*args, **kwargs)

# Global session with source binding
_global_session = None

def configure_requests_source_binding():
    """Configure requests library to bind to specific source IP from environment"""
    global _global_session
    bind_ip = os.getenv("BIND_IP", "0.0.0.0")

    if bind_ip and bind_ip != "0.0.0.0":
        logger.info(f"Configuring requests to bind to source IP: {bind_ip}")
        # Create session with source address adapter
        _global_session = requests_lib.Session()
        adapter = SourceAddressAdapter(bind_ip)
        _global_session.mount("http://", adapter)
        _global_session.mount("https://", adapter)
        logger.info(f"Requests library configured to use source IP: {bind_ip}")
    else:
        logger.info("No source IP binding configured (using default routing)")
        _global_session = requests_lib.Session()

def get_requests_session():
    """Get the configured requests session"""
    return _global_session if _global_session else requests_lib

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

# Initialize scheduler on startup
@app.on_event("startup")
async def startup_event():
    """Initialize scheduler when app starts"""
    configure_requests_source_binding()
    init_scheduler()
    logger.info("Application started with scheduler")

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown scheduler when app stops"""
    shutdown_scheduler()
    logger.info("Application shutdown")

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
        "version": "2.0.0",
        "status": "running",
        "features": ["sync_tests", "async_tasks", "scheduled_tests"],
        "endpoints": {
            "sync": {
                "connectivity": "/test/connectivity",
                "ssl": "/test/ssl",
                "vless": "/test/vless",
                "subscription": "/test/subscription",
                "batch": "/test/batch"
            },
            "async": {
                "submit_subscription": "/test/subscription/async",
                "get_task": "/tasks/{task_id}",
                "list_tasks": "/tasks?status=completed&limit=50"
            },
            "scheduled": {
                "create_subscription": "/scheduled/subscription",
                "list_scheduled": "/scheduled",
                "scheduler_status": "/scheduler/status"
            }
        }
    }

@app.get("/health")
async def health():
    """
    Health check endpoint - tests if THIS network interface can reach the internet

    - Uses configured source IP binding (BIND_IP) to test specific network
    - Returns network_ok=true if can reach external service, false otherwise
    - Useful for distinguishing "VLESS blocked" vs "network down"
    """
    bind_ip = os.getenv("BIND_IP", "0.0.0.0")
    network_name = os.getenv("NETWORK_NAME", "default")

    result = {
        "status": "healthy",
        "network_name": network_name,
        "bind_ip": bind_ip if bind_ip != "0.0.0.0" else None,
        "timestamp": datetime.utcnow().isoformat()
    }

    # Test network connectivity through this specific interface
    try:
        session = get_requests_session()
        response = session.get("https://1.1.1.1", timeout=5)
        result["network_ok"] = response.status_code == 200
        result["network_test"] = "success"
    except Exception as e:
        result["network_ok"] = False
        result["network_test"] = f"failed: {str(e)}"

    return result

@app.get("/myip")
async def get_my_ip():
    """
    Get this worker's outbound IP address (like curl ifconfig.me)

    - Tests actual outbound IP by querying external service
    - Useful for verifying network binding is working correctly
    """
    try:
        # Get the configured requests session
        session = get_requests_session()

        # Try multiple IP check services for redundancy
        services = [
            "https://ifconfig.me",
            "https://api.ipify.org",
            "https://icanhazip.com"
        ]

        for service in services:
            try:
                response = session.get(service, timeout=5)
                if response.status_code == 200:
                    external_ip = response.text.strip()
                    return {
                        "success": True,
                        "external_ip": external_ip,
                        "service": service,
                        "network_name": os.getenv("NETWORK_NAME", "unknown"),
                        "bind_ip": os.getenv("BIND_IP", "0.0.0.0"),
                        "port": os.getenv("PORT", "8000"),
                        "timestamp": datetime.utcnow().isoformat()
                    }
            except:
                continue

        return {"success": False, "error": "All IP check services failed"}

    except Exception as e:
        logger.error(f"Failed to get external IP: {e}")
        return {"success": False, "error": str(e)}

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

@app.post("/test/subscription/async")
async def test_subscription_async(
    request: SubscriptionTestRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Submit subscription test as async task

    - Returns task_id immediately
    - Test runs in background
    - Poll /tasks/{task_id} for results

    This is useful for testing subscriptions with many links (slow)
    """
    logger.info(f"Creating async subscription test task for {request.subscription_url}")

    # Get client info
    client_ip = http_request.client.host if http_request.client else "Unknown"
    user_agent = http_request.headers.get("User-Agent", "Unknown")

    # Create task
    task_id = create_task(
        task_type="subscription",
        request_data={
            "subscription_url": request.subscription_url,
            "timeout": request.timeout,
            "test_vless_links": request.test_vless_links,
            "max_links_to_test": request.max_links_to_test
        },
        db=db,
        client_ip=client_ip,
        user_agent=user_agent
    )

    # Execute task in background thread
    thread = threading.Thread(target=execute_task, args=(task_id,), daemon=True)
    thread.start()

    return {
        "task_id": task_id,
        "status": "pending",
        "message": "Task submitted. Poll /tasks/{task_id} for results."
    }

@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str, db: Session = Depends(get_db)):
    """
    Get status and results of an async task

    - Returns current status: pending, running, completed, failed
    - Returns results when completed
    - Returns error message if failed
    """
    task_data = get_task(task_id, db)

    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")

    return task_data

@app.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    List recent tasks

    - Optional filters: status, task_type
    - Returns up to 'limit' most recent tasks
    """
    query = db.query(TestTask)

    if status:
        query = query.filter(TestTask.status == status)

    if task_type:
        query = query.filter(TestTask.task_type == task_type)

    tasks = query.order_by(TestTask.created_at.desc()).limit(limit).all()

    return {
        "count": len(tasks),
        "tasks": [
            {
                "task_id": task.id,
                "task_type": task.task_type,
                "status": task.status,
                "created_at": task.created_at.isoformat(),
                "completed_at": task.completed_at.isoformat() if task.completed_at else None
            }
            for task in tasks
        ]
    }

@app.post("/scheduled/subscription")
async def create_scheduled_subscription_test(
    name: str,
    subscription_url: str,
    interval_hours: Optional[int] = None,
    cron_expression: Optional[str] = None,
    test_vless_links: bool = False,
    max_links_to_test: int = 0,
    enabled: bool = True,
    db: Session = Depends(get_db)
):
    """
    Create a scheduled subscription test

    - Runs automatically on schedule (interval or cron)
    - interval_hours: Test every N hours (e.g., 6 for every 6 hours)
    - cron_expression: Cron format (e.g., "0 */6 * * *" for every 6 hours)
    - Use either interval_hours OR cron_expression, not both
    """
    if not interval_hours and not cron_expression:
        raise HTTPException(status_code=400, detail="Must provide either interval_hours or cron_expression")

    if interval_hours and cron_expression:
        raise HTTPException(status_code=400, detail="Provide only interval_hours OR cron_expression, not both")

    schedule_type = "interval" if interval_hours else "cron"

    scheduled_id = create_scheduled_test(
        name=name,
        task_type="subscription",
        request_data={
            "subscription_url": subscription_url,
            "timeout": 10,
            "test_vless_links": test_vless_links,
            "max_links_to_test": max_links_to_test
        },
        schedule_type=schedule_type,
        interval_hours=interval_hours,
        cron_expression=cron_expression,
        enabled=enabled
    )

    return {
        "scheduled_id": scheduled_id,
        "name": name,
        "schedule": f"every {interval_hours} hours" if interval_hours else cron_expression,
        "enabled": enabled,
        "message": "Scheduled test created successfully"
    }

@app.get("/scheduled")
async def list_scheduled_tests(db: Session = Depends(get_db)):
    """List all scheduled tests"""
    tests = db.query(ScheduledTest).order_by(ScheduledTest.created_at.desc()).all()

    return {
        "count": len(tests),
        "scheduled_tests": [
            {
                "id": st.id,
                "name": st.name,
                "task_type": st.task_type,
                "enabled": st.enabled,
                "schedule": f"every {st.interval_hours}h" if st.interval_hours else st.cron_expression,
                "last_run": st.last_run_at.isoformat() if st.last_run_at else None,
                "run_count": st.run_count
            }
            for st in tests
        ]
    }

@app.get("/scheduler/status")
async def scheduler_status():
    """Get scheduler status and active jobs"""
    return get_scheduler_status()

@app.get("/orchestrator/check-all-ips")
async def check_all_worker_ips():
    """
    Orchestrator endpoint: Check outbound IP of all workers

    - Queries all 4 workers' /myip endpoints
    - Returns aggregated results showing which network each worker uses
    - Useful for verifying multi-network setup is working correctly
    """
    workers_env = os.getenv("WORKERS", "")
    if not workers_env:
        raise HTTPException(status_code=500, detail="WORKERS environment variable not set. This endpoint only works in orchestrator mode.")

    workers = workers_env.split(",")
    results = []

    for worker_url in workers:
        worker_url = worker_url.strip()
        try:
            response = requests_lib.get(f"{worker_url}/myip", timeout=10)
            if response.status_code == 200:
                results.append({
                    "worker_url": worker_url,
                    "success": True,
                    "data": response.json()
                })
            else:
                results.append({
                    "worker_url": worker_url,
                    "success": False,
                    "error": f"HTTP {response.status_code}"
                })
        except Exception as e:
            results.append({
                "worker_url": worker_url,
                "success": False,
                "error": str(e)
            })

    return {
        "total_workers": len(workers),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "results": results,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/orchestrator/test/connectivity")
async def orchestrator_test_connectivity(request: ConnectivityTestRequest):
    """
    Orchestrator endpoint: Test connectivity from all workers

    - Distributes connectivity test across all workers
    - Returns results from each network (Tele2, MTS, MegaFon, Cable)
    - Useful for comparing connectivity across different networks
    """
    workers_env = os.getenv("WORKERS", "")
    if not workers_env:
        raise HTTPException(status_code=500, detail="WORKERS environment variable not set. This endpoint only works in orchestrator mode.")

    workers = workers_env.split(",")
    results = []

    for worker_url in workers:
        worker_url = worker_url.strip()
        try:
            response = requests_lib.post(
                f"{worker_url}/test/connectivity",
                json=request.dict(),
                timeout=request.timeout + 5
            )
            if response.status_code == 200:
                data = response.json()
                results.append({
                    "worker_url": worker_url,
                    "success": True,
                    "test_result": data
                })
            else:
                results.append({
                    "worker_url": worker_url,
                    "success": False,
                    "error": f"HTTP {response.status_code}"
                })
        except Exception as e:
            results.append({
                "worker_url": worker_url,
                "success": False,
                "error": str(e)
            })

    return {
        "test_type": "connectivity",
        "target": request.target,
        "total_workers": len(workers),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "results": results,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/orchestrator/test/vless")
async def orchestrator_test_vless(request: VLESSTestRequest):
    """
    Orchestrator endpoint: Test VLESS from all workers

    - Distributes VLESS test across all workers
    - Returns results from each network
    - Useful for checking which networks can connect to VLESS servers
    """
    workers_env = os.getenv("WORKERS", "")
    if not workers_env:
        raise HTTPException(status_code=500, detail="WORKERS environment variable not set. This endpoint only works in orchestrator mode.")

    workers = workers_env.split(",")
    results = []

    for worker_url in workers:
        worker_url = worker_url.strip()
        try:
            response = requests_lib.post(
                f"{worker_url}/test/vless",
                json=request.dict(),
                timeout=request.timeout + 10
            )
            if response.status_code == 200:
                data = response.json()
                results.append({
                    "worker_url": worker_url,
                    "success": True,
                    "test_result": data
                })
            else:
                results.append({
                    "worker_url": worker_url,
                    "success": False,
                    "error": f"HTTP {response.status_code}"
                })
        except Exception as e:
            results.append({
                "worker_url": worker_url,
                "success": False,
                "error": str(e)
            })

    return {
        "test_type": "vless",
        "total_workers": len(workers),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "results": results,
        "timestamp": datetime.utcnow().isoformat()
    }

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

# ===== ASYNC JOB ENDPOINTS =====

@app.post("/orchestrator/test/vless/async")
async def orchestrator_test_vless_async(request: VLESSTestRequest, background_tasks: BackgroundTasks):
    """
    Orchestrator endpoint: Submit async VLESS test job

    - Creates a job and returns job_id immediately
    - Tests run in background across all workers
    - Use /orchestrator/job/{job_id} to poll status
    """
    workers_env = os.getenv("WORKERS", "")
    if not workers_env:
        raise HTTPException(status_code=500, detail="WORKERS environment variable not set")

    job_manager = get_job_manager()

    # Create job
    job_id = job_manager.create_job(
        job_type="vless_test",
        params={
            "vless_url": request.vless_url,
            "timeout": request.timeout,
            "test_url": request.test_url
        }
    )

    # Submit job to background processing
    background_tasks.add_task(process_vless_job, job_id, request, workers_env.split(","))

    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Job submitted successfully"
    }

@app.post("/orchestrator/test/connectivity/async")
async def orchestrator_test_connectivity_async(request: ConnectivityTestRequest, background_tasks: BackgroundTasks):
    """
    Orchestrator endpoint: Submit async connectivity test job

    - Creates a job and returns job_id immediately
    - Tests run in background across all workers
    - Use /orchestrator/job/{job_id} to poll status
    """
    workers_env = os.getenv("WORKERS", "")
    if not workers_env:
        raise HTTPException(status_code=500, detail="WORKERS environment variable not set")

    job_manager = get_job_manager()

    # Create job
    job_id = job_manager.create_job(
        job_type="connectivity_test",
        params={
            "target": request.target,
            "port": request.port,
            "timeout": request.timeout,
            "protocol": request.protocol
        }
    )

    # Submit job to background processing
    background_tasks.add_task(process_connectivity_job, job_id, request, workers_env.split(","))

    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Job submitted successfully"
    }

@app.post("/orchestrator/test/ssl/async")
async def orchestrator_test_ssl_async(request: SSLTestRequest, background_tasks: BackgroundTasks):
    """
    Orchestrator endpoint: Submit async SSL test job

    - Creates a job and returns job_id immediately
    - Tests run in background across all workers
    - Use /orchestrator/job/{job_id} to poll status
    """
    workers_env = os.getenv("WORKERS", "")
    if not workers_env:
        raise HTTPException(status_code=500, detail="WORKERS environment variable not set")

    job_manager = get_job_manager()

    # Create job
    job_id = job_manager.create_job(
        job_type="ssl_test",
        params={
            "hostname": request.domain,
            "port": request.port
        }
    )

    # Submit job to background processing
    background_tasks.add_task(process_ssl_job, job_id, request, workers_env.split(","))

    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Job submitted successfully"
    }

@app.post("/orchestrator/test/subscription/async")
async def orchestrator_test_subscription_async(request: SubscriptionTestRequest, background_tasks: BackgroundTasks):
    """
    Orchestrator endpoint: Submit async subscription test job

    - Creates a job and returns job_id immediately
    - Tests run in background across all workers
    - Use /orchestrator/job/{job_id} to poll status
    """
    workers_env = os.getenv("WORKERS", "")
    if not workers_env:
        raise HTTPException(status_code=500, detail="WORKERS environment variable not set")

    job_manager = get_job_manager()

    # Create job
    job_id = job_manager.create_job(
        job_type="subscription_test",
        params={
            "subscription_url": request.subscription_url,
            "timeout": request.timeout,
            "test_vless_links": request.test_vless_links,
            "max_links_to_test": request.max_links_to_test
        }
    )

    # Submit job to background processing
    background_tasks.add_task(process_subscription_job, job_id, request, workers_env.split(","))

    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Job submitted successfully"
    }

@app.get("/orchestrator/job/{job_id}")
async def get_job_status(job_id: str):
    """
    Get status of an async job with aggregated results

    - Returns current status, progress
    - For vless_test jobs: automatically aggregates worker results
    - Job data expires after 1 hour
    """
    job_manager = get_job_manager()
    job_data = job_manager.get_job(job_id)

    if job_data is None:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    # If this is an async distributed test job, aggregate worker results
    if job_data.get('job_type') in ['vless_test', 'connectivity_test', 'ssl_test', 'subscription_test']:
        submission_results = job_data.get('result', {}).get('results', [])
        worker_results = []

        for submission in submission_results:
            worker_job_id = submission.get('worker_job_id')
            worker_url = submission.get('worker_url')

            if not worker_job_id or not worker_url:
                continue

            # Fetch worker job data from Redis
            worker_job = job_manager.get_job(worker_job_id)

            if worker_job:
                worker_results.append({
                    'worker_url': worker_url,
                    'worker_job_id': worker_job_id,
                    'status': worker_job.get('status'),
                    'test_result': worker_job.get('result'),
                    'error': worker_job.get('error')
                })
            else:
                # Worker job not found (may have expired or failed to create)
                worker_results.append({
                    'worker_url': worker_url,
                    'worker_job_id': worker_job_id,
                    'status': 'unknown',
                    'test_result': None,
                    'error': 'Worker job not found in Redis'
                })

        # Count successful tests
        successful = sum(1 for r in worker_results
                        if r.get('test_result') and r.get('test_result', {}).get('success') == True)

        # Return enhanced job data with aggregated results
        return {
            'job_id': job_data.get('job_id'),
            'job_type': job_data.get('job_type'),
            'status': job_data.get('status'),
            'progress': job_data.get('progress'),
            'created_at': job_data.get('created_at'),
            'updated_at': job_data.get('updated_at'),
            'total_workers': len(worker_results),
            'successful': successful,
            'failed': len(worker_results) - successful,
            'worker_results': worker_results,
            'error': job_data.get('error')
        }

    # For other job types, return raw data
    return job_data

@app.post("/worker/job/vless")
async def worker_process_vless_job(request: Dict, background_tasks: BackgroundTasks):
    """
    Worker endpoint: Process VLESS test job with Redis state updates

    - Accepts job_id and test params
    - Processes test in background
    - Updates job state in Redis
    """
    job_id = request.get("job_id")
    vless_url = request.get("vless_url")
    timeout = request.get("timeout", 20)
    test_url = request.get("test_url", "https://httpbin.org/get")

    if not job_id or not vless_url:
        raise HTTPException(status_code=400, detail="job_id and vless_url required")

    job_manager = get_job_manager()

    # Update job to running
    job_manager.update_job(job_id, status="running", progress=0)

    # Process in background
    background_tasks.add_task(process_worker_vless_test, job_id, vless_url, timeout, test_url)

    return {"status": "accepted", "job_id": job_id}

@app.post("/worker/job/connectivity")
async def worker_process_connectivity_job(request: Dict, background_tasks: BackgroundTasks):
    """
    Worker endpoint: Process connectivity test job with Redis state updates
    """
    job_id = request.get("job_id")
    target = request.get("target")
    port = request.get("port", 443)
    timeout = request.get("timeout", 10)
    protocol = request.get("protocol", "https")

    if not job_id or not target:
        raise HTTPException(status_code=400, detail="job_id and target required")

    job_manager = get_job_manager()
    job_manager.update_job(job_id, status="running", progress=0)

    background_tasks.add_task(process_worker_connectivity_test, job_id, target, port, timeout, protocol)

    return {"status": "accepted", "job_id": job_id}

@app.post("/worker/job/ssl")
async def worker_process_ssl_job(request: Dict, background_tasks: BackgroundTasks):
    """
    Worker endpoint: Process SSL test job with Redis state updates
    """
    job_id = request.get("job_id")
    hostname = request.get("hostname")
    port = request.get("port", 443)

    if not job_id or not hostname:
        raise HTTPException(status_code=400, detail="job_id and hostname required")

    job_manager = get_job_manager()
    job_manager.update_job(job_id, status="running", progress=0)

    background_tasks.add_task(process_worker_ssl_test, job_id, hostname, port)

    return {"status": "accepted", "job_id": job_id}

@app.post("/worker/job/subscription")
async def worker_process_subscription_job(request: Dict, background_tasks: BackgroundTasks):
    """
    Worker endpoint: Process subscription test job with Redis state updates
    """
    job_id = request.get("job_id")
    subscription_url = request.get("subscription_url")
    timeout = request.get("timeout", 10)
    test_vless_links = request.get("test_vless_links", False)
    max_links_to_test = request.get("max_links_to_test", 3)

    if not job_id or not subscription_url:
        raise HTTPException(status_code=400, detail="job_id and subscription_url required")

    job_manager = get_job_manager()
    job_manager.update_job(job_id, status="running", progress=0)

    background_tasks.add_task(process_worker_subscription_test, job_id, subscription_url, timeout, test_vless_links, max_links_to_test)

    return {"status": "accepted", "job_id": job_id}

# Background task functions

async def process_vless_job(job_id: str, request: VLESSTestRequest, workers: List[str]):
    """Background task to process VLESS test across all workers"""
    job_manager = get_job_manager()

    try:
        job_manager.update_job(job_id, status="running", progress=10)

        results = []
        total_workers = len(workers)

        # Create all worker sub-jobs in Redis BEFORE distributing
        for idx, worker_url in enumerate(workers):
            worker_job_id = f"{job_id}_{idx}"
            job_manager.create_job(
                job_type="vless_test_worker",
                params={
                    "vless_url": request.vless_url,
                    "timeout": request.timeout,
                    "test_url": request.test_url,
                    "worker_url": worker_url.strip()
                },
                job_id=worker_job_id
            )

        # Use async httpx to submit jobs to all workers in parallel
        # Increased timeout to account for worker startup and Redis operations
        async with httpx.AsyncClient(timeout=15.0) as client:

            async def submit_to_worker(idx: int, worker_url: str):
                """Submit job to a single worker"""
                worker_url = worker_url.strip()
                worker_job_id = f"{job_id}_{idx}"
                try:
                    # Submit job to worker
                    payload = {
                        "job_id": worker_job_id,
                        "vless_url": request.vless_url,
                        "timeout": request.timeout,
                        "test_url": request.test_url
                    }
                    logger.info(f"Submitting job {worker_job_id} to worker {worker_url}")
                    logger.debug(f"Payload: {payload}")

                    response = await client.post(
                        f"{worker_url}/worker/job/vless",
                        json=payload
                    )
                    logger.info(f"Worker {worker_url} responded with status {response.status_code}")

                    if response.status_code == 200:
                        return {
                            "worker_url": worker_url,
                            "status": "submitted",
                            "worker_job_id": worker_job_id
                        }
                    else:
                        response_text = response.text
                        logger.error(f"Worker {worker_url} returned {response.status_code}: {response_text}")
                        return {
                            "worker_url": worker_url,
                            "status": "failed",
                            "error": f"HTTP {response.status_code}: {response_text}"
                        }
                except Exception as e:
                    logger.error(f"Failed to submit job to worker {worker_url}: {e}")
                    return {
                        "worker_url": worker_url,
                        "status": "failed",
                        "error": str(e)
                    }

            # Submit to all workers in parallel
            tasks = [submit_to_worker(idx, worker_url) for idx, worker_url in enumerate(workers)]
            results = await asyncio.gather(*tasks)

            # Update progress to 100% (all submissions attempted)
            job_manager.update_job(job_id, progress=100)

        # Mark as completed
        job_manager.update_job(
            job_id,
            status="completed",
            progress=100,
            result={
                "total_workers": total_workers,
                "submitted": sum(1 for r in results if r.get("status") == "submitted"),
                "results": results
            }
        )

    except Exception as e:
        logger.error(f"Error processing job {job_id}: {e}")
        job_manager.update_job(job_id, status="failed", error=str(e))

async def process_worker_vless_test(job_id: str, vless_url: str, timeout: int, test_url: str):
    """Background task for worker to process VLESS test and update Redis"""
    job_manager = get_job_manager()

    try:
        job_manager.update_job(job_id, status="running", progress=25)

        # Run the actual test
        tester = VLESSTester()
        result = tester.test(vless_url, timeout, test_url)

        job_manager.update_job(job_id, progress=75)

        # Store result
        job_manager.update_job(
            job_id,
            status="completed",
            progress=100,
            result=result
        )

    except Exception as e:
        logger.error(f"Error in worker job {job_id}: {e}")
        job_manager.update_job(job_id, status="failed", error=str(e))

async def process_connectivity_job(job_id: str, request: ConnectivityTestRequest, workers: List[str]):
    """Background task to process connectivity test across all workers"""
    job_manager = get_job_manager()

    try:
        job_manager.update_job(job_id, status="running", progress=10)

        results = []
        total_workers = len(workers)

        # Create all worker sub-jobs in Redis
        for idx, worker_url in enumerate(workers):
            worker_job_id = f"{job_id}_{idx}"
            job_manager.create_job(
                job_type="connectivity_test_worker",
                params={
                    "target": request.target,
                    "port": request.port,
                    "timeout": request.timeout,
                    "protocol": request.protocol,
                    "worker_url": worker_url.strip()
                },
                job_id=worker_job_id
            )

        # Submit to all workers in parallel
        async with httpx.AsyncClient(timeout=15.0) as client:
            async def submit_to_worker(idx: int, worker_url: str):
                worker_url = worker_url.strip()
                worker_job_id = f"{job_id}_{idx}"
                try:
                    payload = {
                        "job_id": worker_job_id,
                        "target": request.target,
                        "port": request.port,
                        "timeout": request.timeout,
                        "protocol": request.protocol
                    }
                    logger.info(f"Submitting connectivity job {worker_job_id} to worker {worker_url}")

                    response = await client.post(f"{worker_url}/worker/job/connectivity", json=payload)
                    logger.info(f"Worker {worker_url} responded with status {response.status_code}")

                    if response.status_code == 200:
                        return {"worker_url": worker_url, "status": "submitted", "worker_job_id": worker_job_id}
                    else:
                        return {"worker_url": worker_url, "status": "failed", "error": f"HTTP {response.status_code}"}
                except Exception as e:
                    logger.error(f"Failed to submit job to worker {worker_url}: {e}")
                    return {"worker_url": worker_url, "status": "failed", "error": str(e)}

            tasks = [submit_to_worker(idx, worker_url) for idx, worker_url in enumerate(workers)]
            results = await asyncio.gather(*tasks)
            job_manager.update_job(job_id, progress=100)

        job_manager.update_job(job_id, status="completed", result={"total_workers": total_workers, "submitted": sum(1 for r in results if r.get("status") == "submitted"), "results": results})

    except Exception as e:
        logger.error(f"Error processing connectivity job {job_id}: {e}")
        job_manager.update_job(job_id, status="failed", error=str(e))

async def process_ssl_job(job_id: str, request: SSLTestRequest, workers: List[str]):
    """Background task to process SSL test across all workers"""
    job_manager = get_job_manager()

    try:
        job_manager.update_job(job_id, status="running", progress=10)

        results = []
        total_workers = len(workers)

        # Create all worker sub-jobs in Redis
        for idx, worker_url in enumerate(workers):
            worker_job_id = f"{job_id}_{idx}"
            job_manager.create_job(
                job_type="ssl_test_worker",
                params={
                    "hostname": request.domain,
                    "port": request.port,
                    "worker_url": worker_url.strip()
                },
                job_id=worker_job_id
            )

        # Submit to all workers in parallel
        async with httpx.AsyncClient(timeout=15.0) as client:
            async def submit_to_worker(idx: int, worker_url: str):
                worker_url = worker_url.strip()
                worker_job_id = f"{job_id}_{idx}"
                try:
                    payload = {
                        "job_id": worker_job_id,
                        "hostname": request.domain,
                        "port": request.port
                    }
                    logger.info(f"Submitting SSL job {worker_job_id} to worker {worker_url}")

                    response = await client.post(f"{worker_url}/worker/job/ssl", json=payload)
                    logger.info(f"Worker {worker_url} responded with status {response.status_code}")

                    if response.status_code == 200:
                        return {"worker_url": worker_url, "status": "submitted", "worker_job_id": worker_job_id}
                    else:
                        return {"worker_url": worker_url, "status": "failed", "error": f"HTTP {response.status_code}"}
                except Exception as e:
                    logger.error(f"Failed to submit job to worker {worker_url}: {e}")
                    return {"worker_url": worker_url, "status": "failed", "error": str(e)}

            tasks = [submit_to_worker(idx, worker_url) for idx, worker_url in enumerate(workers)]
            results = await asyncio.gather(*tasks)
            job_manager.update_job(job_id, progress=100)

        job_manager.update_job(job_id, status="completed", result={"total_workers": total_workers, "submitted": sum(1 for r in results if r.get("status") == "submitted"), "results": results})

    except Exception as e:
        logger.error(f"Error processing SSL job {job_id}: {e}")
        job_manager.update_job(job_id, status="failed", error=str(e))

async def process_worker_connectivity_test(job_id: str, target: str, port: int, timeout: int, protocol: str):
    """Background task for worker to process connectivity test and update Redis"""
    job_manager = get_job_manager()

    try:
        job_manager.update_job(job_id, status="running", progress=25)

        # Run the actual test
        tester = ConnectivityTester()
        result = tester.test(target, port, timeout, protocol)

        job_manager.update_job(job_id, progress=75)

        # Store result
        job_manager.update_job(job_id, status="completed", progress=100, result=result)

    except Exception as e:
        logger.error(f"Error in worker connectivity job {job_id}: {e}")
        job_manager.update_job(job_id, status="failed", error=str(e))

async def process_worker_ssl_test(job_id: str, hostname: str, port: int):
    """Background task for worker to process SSL test and update Redis"""
    job_manager = get_job_manager()

    try:
        job_manager.update_job(job_id, status="running", progress=25)

        # Run the actual test
        checker = SSLChecker()
        result = checker.check(hostname, port)

        job_manager.update_job(job_id, progress=75)

        # Store result
        job_manager.update_job(job_id, status="completed", progress=100, result=result)

    except Exception as e:
        logger.error(f"Error in worker SSL job {job_id}: {e}")
        job_manager.update_job(job_id, status="failed", error=str(e))

async def process_subscription_job(job_id: str, request: SubscriptionTestRequest, workers: List[str]):
    """Background task to process subscription test across all workers"""
    job_manager = get_job_manager()

    try:
        job_manager.update_job(job_id, status="running", progress=10)

        results = []
        total_workers = len(workers)

        # Create all worker sub-jobs in Redis
        for idx, worker_url in enumerate(workers):
            worker_job_id = f"{job_id}_{idx}"
            job_manager.create_job(
                job_type="subscription_test_worker",
                params={
                    "subscription_url": request.subscription_url,
                    "timeout": request.timeout,
                    "test_vless_links": request.test_vless_links,
                    "max_links_to_test": request.max_links_to_test,
                    "worker_url": worker_url.strip()
                },
                job_id=worker_job_id
            )

        # Submit to all workers in parallel
        async with httpx.AsyncClient(timeout=15.0) as client:
            async def submit_to_worker(idx: int, worker_url: str):
                worker_url = worker_url.strip()
                worker_job_id = f"{job_id}_{idx}"
                try:
                    payload = {
                        "job_id": worker_job_id,
                        "subscription_url": request.subscription_url,
                        "timeout": request.timeout,
                        "test_vless_links": request.test_vless_links,
                        "max_links_to_test": request.max_links_to_test
                    }
                    logger.info(f"Submitting subscription job {worker_job_id} to worker {worker_url}")

                    response = await client.post(f"{worker_url}/worker/job/subscription", json=payload)
                    logger.info(f"Worker {worker_url} responded with status {response.status_code}")

                    if response.status_code == 200:
                        return {"worker_url": worker_url, "status": "submitted", "worker_job_id": worker_job_id}
                    else:
                        return {"worker_url": worker_url, "status": "failed", "worker_job_id": worker_job_id, "error": f"HTTP {response.status_code}"}
                except Exception as e:
                    logger.error(f"Failed to submit job to worker {worker_url}: {e}")
                    return {"worker_url": worker_url, "status": "failed", "worker_job_id": worker_job_id, "error": str(e)}

            tasks = [submit_to_worker(idx, worker_url) for idx, worker_url in enumerate(workers)]
            results = await asyncio.gather(*tasks)
            job_manager.update_job(job_id, progress=100)

        job_manager.update_job(job_id, status="completed", result={"total_workers": total_workers, "submitted": sum(1 for r in results if r.get("status") == "submitted"), "results": results})

    except Exception as e:
        logger.error(f"Error processing subscription job {job_id}: {e}")
        job_manager.update_job(job_id, status="failed", error=str(e))

async def process_worker_subscription_test(job_id: str, subscription_url: str, timeout: int, test_vless_links: bool, max_links_to_test: int):
    """Background task for worker to process subscription test and update Redis"""
    job_manager = get_job_manager()

    try:
        job_manager.update_job(job_id, status="running", progress=25)

        # Run the actual test using existing subscription test logic
        tester = SubscriptionTester()
        result = tester.test(
            subscription_url=subscription_url,
            timeout=timeout,
            test_links=test_vless_links,
            max_links=max_links_to_test
        )

        job_manager.update_job(job_id, progress=75)

        # Store result
        job_manager.update_job(job_id, status="completed", progress=100, result=result)

    except Exception as e:
        logger.error(f"Error in worker subscription job {job_id}: {e}")
        job_manager.update_job(job_id, status="failed", error=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
