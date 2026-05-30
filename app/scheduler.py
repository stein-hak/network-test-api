"""
APScheduler integration for periodic scheduled tests
"""
import logging
import uuid
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import json
import os
import httpx
import asyncio

from app.database import SessionLocal, ScheduledTest
from app.tasks import create_task, execute_task

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


def init_scheduler():
    """Initialize the APScheduler"""
    global scheduler

    if scheduler is not None:
        logger.warning("Scheduler already initialized")
        return scheduler

    scheduler = BackgroundScheduler()
    scheduler.start()
    logger.info("APScheduler started")

    # Load and schedule all enabled scheduled tests from database
    load_scheduled_tests()

    return scheduler


def load_scheduled_tests():
    """Load all enabled scheduled tests from database and add to scheduler"""
    db = SessionLocal()

    try:
        scheduled_tests = db.query(ScheduledTest).filter(ScheduledTest.enabled == True).all()

        logger.info(f"Loading {len(scheduled_tests)} scheduled tests")

        for st in scheduled_tests:
            add_scheduled_test_to_scheduler(st)

    finally:
        db.close()


def add_scheduled_test_to_scheduler(scheduled_test: ScheduledTest):
    """
    Add a scheduled test to the APScheduler

    Args:
        scheduled_test: ScheduledTest database model
    """
    if scheduler is None:
        logger.error("Scheduler not initialized")
        return

    job_id = f"scheduled_test_{scheduled_test.id}"

    # Remove existing job if present
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    # Determine trigger type
    if scheduled_test.schedule_type == "interval":
        trigger = IntervalTrigger(hours=scheduled_test.interval_hours)
    elif scheduled_test.schedule_type == "cron":
        # Parse cron expression
        # Format: "minute hour day month day_of_week"
        # Example: "0 */6 * * *" = every 6 hours
        parts = scheduled_test.cron_expression.split()
        trigger = CronTrigger(
            minute=parts[0] if len(parts) > 0 else "*",
            hour=parts[1] if len(parts) > 1 else "*",
            day=parts[2] if len(parts) > 2 else "*",
            month=parts[3] if len(parts) > 3 else "*",
            day_of_week=parts[4] if len(parts) > 4 else "*"
        )
    else:
        logger.error(f"Unknown schedule type: {scheduled_test.schedule_type}")
        return

    # Add job to scheduler
    scheduler.add_job(
        func=run_scheduled_test,
        trigger=trigger,
        id=job_id,
        args=[scheduled_test.id],
        name=scheduled_test.name,
        replace_existing=True
    )

    logger.info(f"Added scheduled test '{scheduled_test.name}' (ID: {scheduled_test.id}) to scheduler")


def run_scheduled_test(scheduled_test_id: str):
    """
    Execute a scheduled test

    In orchestrator mode (WORKERS env var set): Creates distributed Redis job via /orchestrator/test/vless/async
    In worker mode: Executes locally via legacy task system

    Args:
        scheduled_test_id: ID of the ScheduledTest
    """
    db = SessionLocal()

    try:
        # Get scheduled test config
        st = db.query(ScheduledTest).filter(ScheduledTest.id == scheduled_test_id).first()

        if not st or not st.enabled:
            logger.warning(f"Scheduled test {scheduled_test_id} not found or disabled")
            return

        logger.info(f"Running scheduled test: {st.name}")

        # Parse request data
        request_data = json.loads(st.request_data)

        # Check if running in orchestrator mode
        workers_env = os.getenv("WORKERS", "")

        if workers_env:
            # Orchestrator mode: Create distributed job via HTTP
            logger.info(f"Orchestrator mode detected, creating distributed job for '{st.name}'")

            # Run async HTTP request in sync context
            job_id = asyncio.run(_create_orchestrator_job(st.task_type, request_data))

            # Update scheduled test metadata with job_id
            st.last_run_at = datetime.utcnow()
            st.last_task_id = job_id  # Store job_id instead of task_id
            st.run_count += 1
            db.commit()

            logger.info(f"Scheduled test '{st.name}' submitted to orchestrator. Job ID: {job_id}")
        else:
            # Worker mode: Local execution (legacy)
            logger.info(f"Worker mode detected, executing locally for '{st.name}'")

            # Create task
            task_id = create_task(
                task_type=st.task_type,
                request_data=request_data,
                db=db,
                client_ip="scheduler",
                user_agent=f"Scheduled:{st.name}"
            )

            # Update scheduled test metadata
            st.last_run_at = datetime.utcnow()
            st.last_task_id = task_id
            st.run_count += 1
            db.commit()

            # Execute task locally
            execute_task(task_id)

            logger.info(f"Scheduled test '{st.name}' completed. Task ID: {task_id}")

    except Exception as e:
        logger.error(f"Error running scheduled test {scheduled_test_id}: {e}", exc_info=True)

    finally:
        db.close()


async def _create_orchestrator_job(task_type: str, request_data: dict) -> str:
    """
    Create a distributed job via orchestrator HTTP API

    Args:
        task_type: Type of test (vless, subscription, etc.)
        request_data: Test parameters

    Returns:
        job_id from orchestrator
    """
    # Map task_type to orchestrator endpoint
    endpoint_map = {
        "vless": "/orchestrator/test/vless/async",
        "subscription": "/orchestrator/test/subscription/async"
    }

    endpoint = endpoint_map.get(task_type)
    if not endpoint:
        raise ValueError(f"Unsupported task_type for orchestrator mode: {task_type}")

    # Make HTTP request to localhost orchestrator
    orchestrator_url = f"http://localhost:8000{endpoint}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(orchestrator_url, json=request_data)
        response.raise_for_status()

        result = response.json()
        job_id = result.get("job_id")

        if not job_id:
            raise ValueError(f"No job_id in orchestrator response: {result}")

        return job_id


def create_scheduled_test(
    name: str,
    task_type: str,
    request_data: dict,
    schedule_type: str,
    interval_hours: int = None,
    cron_expression: str = None,
    enabled: bool = True
) -> str:
    """
    Create a new scheduled test

    Args:
        name: Human-readable name
        task_type: Type of test (subscription, vless, etc.)
        request_data: Test parameters
        schedule_type: "interval" or "cron"
        interval_hours: For interval scheduling
        cron_expression: For cron scheduling
        enabled: Whether to enable immediately

    Returns:
        Scheduled test ID
    """
    db = SessionLocal()

    try:
        scheduled_test_id = str(uuid.uuid4())

        st = ScheduledTest(
            id=scheduled_test_id,
            name=name,
            task_type=task_type,
            request_data=json.dumps(request_data),
            schedule_type=schedule_type,
            interval_hours=interval_hours,
            cron_expression=cron_expression,
            enabled=enabled
        )

        db.add(st)
        db.commit()

        logger.info(f"Created scheduled test '{name}' (ID: {scheduled_test_id})")

        # Add to scheduler if enabled
        if enabled:
            add_scheduled_test_to_scheduler(st)

        return scheduled_test_id

    finally:
        db.close()


def get_scheduler_status():
    """Get scheduler status and job list"""
    if scheduler is None:
        return {"status": "not_initialized", "jobs": []}

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })

    return {
        "status": "running" if scheduler.running else "stopped",
        "job_count": len(jobs),
        "jobs": jobs
    }


def shutdown_scheduler():
    """Shutdown the scheduler gracefully"""
    global scheduler

    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        logger.info("Scheduler shut down")
