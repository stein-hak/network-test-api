#!/usr/bin/env python3
"""
Synchronous Network Test API Client
"""

import requests
import base64
from typing import Optional, Dict, List, Any


class NetworkTestClient:
    """Synchronous client for network-test-api orchestrator"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize the client

        Args:
            base_url: Base URL of the orchestrator
        """
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()

    def check_all_ips(self) -> Dict[str, Any]:
        """Check outbound IPs of all workers"""
        response = self.session.get(f"{self.base_url}/orchestrator/check-all-ips")
        response.raise_for_status()
        return response.json()

    def test_connectivity(
        self,
        target: str,
        port: int = 443,
        timeout: int = 10,
        protocol: str = "https"
    ) -> Dict[str, Any]:
        """Test connectivity from all workers"""
        payload = {
            "target": target,
            "port": port,
            "timeout": timeout,
            "protocol": protocol
        }
        response = self.session.post(
            f"{self.base_url}/orchestrator/test/connectivity",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    def test_vless(
        self,
        vless_url: str,
        timeout: int = 20,
        test_url: str = "https://httpbin.org/get"
    ) -> Dict[str, Any]:
        """Test VLESS connection from all workers"""
        payload = {
            "vless_url": vless_url,
            "timeout": timeout,
            "test_url": test_url
        }
        response = self.session.post(
            f"{self.base_url}/orchestrator/test/vless",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    def parse_subscription(self, subscription_url: str) -> List[str]:
        """Fetch and parse a VLESS subscription"""
        response = requests.get(subscription_url)
        response.raise_for_status()
        decoded = base64.b64decode(response.text).decode('utf-8')
        return [line.strip() for line in decoded.split('\n') if line.strip()]

    def close(self):
        """Close the session"""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
