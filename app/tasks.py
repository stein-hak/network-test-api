"""
Background task execution for async testing
"""
import json
import uuid
import logging
from datetime import datetime
from typing import Dict, Optional
from sqlalchemy.orm import Session

from app.database import TestTask, SessionLocal
from app.testers.subscription import SubscriptionTester
from app.testers.vless_tester import VLESSTester
from app.testers.ssl_checker import SSLChecker
from app.testers.connectivity import ConnectivityTester

logger = logging.getLogger(__name__)


def create_task(task_type: str, request_data: Dict, db: Session, client_ip: str = None, user_agent: str = None) -> str:
    """
    Create a new test task

    Args:
        task_type: Type of test (subscription, vless, ssl, connectivity)
        request_data: Test parameters
        db: Database session
        client_ip: Client IP address
        user_agent: Client user agent

    Returns:
        Task ID
    """
    task_id = str(uuid.uuid4())

    task = TestTask(
        id=task_id,
        task_type=task_type,
        status="pending",
        request_data=json.dumps(request_data),
        client_ip=client_ip,
        user_agent=user_agent
    )

    db.add(task)
    db.commit()

    logger.info(f"Created task {task_id} of type {task_type}")
    return task_id


def get_task(task_id: str, db: Session) -> Optional[Dict]:
    """
    Get task by ID

    Args:
        task_id: Task ID
        db: Database session

    Returns:
        Task data dict or None
    """
    task = db.query(TestTask).filter(TestTask.id == task_id).first()

    if not task:
        return None

    result = {
        "task_id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }

    # Add request data
    try:
        result["request"] = json.loads(task.request_data)
    except:
        result["request"] = {}

    # Add results if completed
    if task.status == "completed" and task.result_data:
        try:
            result["result"] = json.loads(task.result_data)
        except:
            result["result"] = None

    # Add error if failed
    if task.status == "failed":
        result["error"] = task.error

    return result


def execute_subscription_test(task_id: str):
    """Execute subscription test in background"""
    db = SessionLocal()

    try:
        # Get task
        task = db.query(TestTask).filter(TestTask.id == task_id).first()
        if not task:
            logger.error(f"Task {task_id} not found")
            return

        # Update status to running
        task.status = "running"
        task.started_at = datetime.utcnow()
        db.commit()

        logger.info(f"Starting subscription test for task {task_id}")

        # Parse request data
        request_data = json.loads(task.request_data)

        # Execute test
        tester = SubscriptionTester()
        result = tester.test(
            subscription_url=request_data.get("subscription_url"),
            timeout=request_data.get("timeout", 10),
            test_links=request_data.get("test_vless_links", False),
            max_links=request_data.get("max_links_to_test", 3)
        )

        # Update task with results
        task.status = "completed"
        task.completed_at = datetime.utcnow()
        task.result_data = json.dumps(result)
        db.commit()

        logger.info(f"Completed subscription test for task {task_id}")

    except Exception as e:
        logger.error(f"Error executing task {task_id}: {e}", exc_info=True)

        # Update task with error
        task.status = "failed"
        task.completed_at = datetime.utcnow()
        task.error = str(e)
        db.commit()

    finally:
        db.close()


def execute_vless_test(task_id: str):
    """Execute VLESS test in background"""
    db = SessionLocal()

    try:
        task = db.query(TestTask).filter(TestTask.id == task_id).first()
        if not task:
            return

        task.status = "running"
        task.started_at = datetime.utcnow()
        db.commit()

        request_data = json.loads(task.request_data)

        tester = VLESSTester()
        result = tester.test(
            vless_url=request_data.get("vless_url"),
            timeout=request_data.get("timeout", 15)
        )

        task.status = "completed"
        task.completed_at = datetime.utcnow()
        task.result_data = json.dumps(result)
        db.commit()

    except Exception as e:
        logger.error(f"Error executing VLESS test {task_id}: {e}")
        task.status = "failed"
        task.completed_at = datetime.utcnow()
        task.error = str(e)
        db.commit()

    finally:
        db.close()


def execute_task(task_id: str):
    """
    Execute a task based on its type

    Args:
        task_id: Task ID to execute
    """
    db = SessionLocal()

    try:
        task = db.query(TestTask).filter(TestTask.id == task_id).first()
        if not task:
            logger.error(f"Task {task_id} not found")
            return

        task_type = task.task_type

        # Route to appropriate test executor
        if task_type == "subscription":
            execute_subscription_test(task_id)
        elif task_type == "vless":
            execute_vless_test(task_id)
        else:
            logger.error(f"Unknown task type: {task_type}")

    finally:
        db.close()
