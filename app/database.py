"""
Database models and session management for async task storage
"""
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

# Database URL - use SQLite by default
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test_tasks.db")

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


class TestTask(Base):
    """Model for async test tasks"""
    __tablename__ = "test_tasks"

    id = Column(String, primary_key=True, index=True)
    task_type = Column(String, nullable=False)  # "subscription", "vless", "ssl", etc.
    status = Column(String, nullable=False, default="pending")  # pending, running, completed, failed

    # Request parameters (JSON)
    request_data = Column(Text, nullable=False)

    # Results (JSON)
    result_data = Column(Text, nullable=True)

    # Error message if failed
    error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Scheduling
    is_scheduled = Column(Boolean, default=False)
    schedule_cron = Column(String, nullable=True)  # Cron expression
    schedule_interval_hours = Column(Integer, nullable=True)  # Interval in hours

    # Metadata
    client_ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)


class ScheduledTest(Base):
    """Model for scheduled periodic tests"""
    __tablename__ = "scheduled_tests"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)  # Human-readable name
    task_type = Column(String, nullable=False)  # "subscription", "vless", etc.
    enabled = Column(Boolean, default=True)

    # Request parameters (JSON)
    request_data = Column(Text, nullable=False)

    # Schedule configuration
    schedule_type = Column(String, nullable=False)  # "interval" or "cron"
    interval_hours = Column(Integer, nullable=True)  # For interval scheduling
    cron_expression = Column(String, nullable=True)  # For cron scheduling

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_run_at = Column(DateTime, nullable=True)
    last_task_id = Column(String, nullable=True)  # ID of last executed task

    # Run count
    run_count = Column(Integer, default=0)


# Create tables
Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
