"""
Network Test Client Library

A Python client for interacting with the network-test-api orchestrator.
Provides both sync and async interfaces for testing connectivity and VLESS links
across multiple networks.
"""

from .sync_client import NetworkTestClient
from .async_client import AsyncNetworkTestClient

__version__ = "1.0.0"
__all__ = ["NetworkTestClient", "AsyncNetworkTestClient"]
