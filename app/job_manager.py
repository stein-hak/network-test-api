#!/usr/bin/env python3
"""
Redis-based Job Manager for async task processing
"""

import redis
import json
import uuid
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class JobManager:
    """Manages async jobs using Redis for state storage"""

    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize job manager with Redis connection

        Args:
            redis_url: Redis connection URL (default: from REDIS_URL env or localhost)
        """
        if redis_url is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.job_ttl = 3600  # Jobs expire after 1 hour

    def create_job(self, job_type: str, params: Dict[str, Any], job_id: Optional[str] = None) -> str:
        """
        Create a new job

        Args:
            job_type: Type of job (e.g., 'vless_test', 'connectivity_test')
            params: Job parameters
            job_id: Optional specific job_id to use (default: auto-generate UUID)

        Returns:
            job_id: UUID of created job
        """
        if job_id is None:
            job_id = str(uuid.uuid4())
        else:
            job_id = str(job_id)

        job_data = {
            'job_id': job_id,
            'job_type': job_type,
            'status': 'pending',
            'params': params,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'progress': 0,
            'result': None,
            'error': None
        }

        # Store job data in Redis
        key = f"job:{job_id}"
        self.redis_client.setex(
            key,
            self.job_ttl,
            json.dumps(job_data)
        )

        logger.info(f"Created job {job_id} of type {job_type}")
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get job status and data

        Args:
            job_id: Job UUID

        Returns:
            Job data dict or None if not found
        """
        key = f"job:{job_id}"
        data = self.redis_client.get(key)

        if data is None:
            return None

        return json.loads(data)

    def update_job(
        self,
        job_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> bool:
        """
        Update job status

        Args:
            job_id: Job UUID
            status: New status ('pending', 'running', 'completed', 'failed')
            progress: Progress percentage (0-100)
            result: Job result data
            error: Error message if failed

        Returns:
            True if updated, False if job not found
        """
        job_data = self.get_job(job_id)
        if job_data is None:
            logger.warning(f"Attempted to update non-existent job {job_id}")
            return False

        # Update fields
        if status is not None:
            job_data['status'] = status
        if progress is not None:
            job_data['progress'] = progress
        if result is not None:
            job_data['result'] = result
        if error is not None:
            job_data['error'] = error

        job_data['updated_at'] = datetime.utcnow().isoformat()

        # Save back to Redis
        key = f"job:{job_id}"
        self.redis_client.setex(
            key,
            self.job_ttl,
            json.dumps(job_data)
        )

        logger.info(f"Updated job {job_id}: status={status}, progress={progress}")
        return True

    def delete_job(self, job_id: str) -> bool:
        """
        Delete a job

        Args:
            job_id: Job UUID

        Returns:
            True if deleted, False if not found
        """
        key = f"job:{job_id}"
        result = self.redis_client.delete(key)
        return result > 0

    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """
        Clean up jobs older than specified hours

        Args:
            max_age_hours: Maximum age in hours
        """
        # Redis TTL handles this automatically, but we can add manual cleanup if needed
        pass

# Global job manager instance
_job_manager = None

def get_job_manager() -> JobManager:
    """Get global job manager instance"""
    global _job_manager
    if _job_manager is None:
        _job_manager = JobManager()
    return _job_manager
