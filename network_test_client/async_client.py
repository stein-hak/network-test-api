#!/usr/bin/env python3
"""
Asynchronous Network Test API Client
"""

import httpx
import base64
import asyncio
from typing import Optional, Dict, List, Any


class AsyncNetworkTestClient:
    """Asynchronous client for network-test-api orchestrator"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize the async client

        Args:
            base_url: Base URL of the orchestrator
        """
        self.base_url = base_url.rstrip('/')
        self.client = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=60.0)
        return self

    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()

    async def check_all_ips(self) -> Dict[str, Any]:
        """Check outbound IPs of all workers"""
        response = await self.client.get(f"{self.base_url}/orchestrator/check-all-ips")
        response.raise_for_status()
        return response.json()

    async def test_connectivity(
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
        response = await self.client.post(
            f"{self.base_url}/orchestrator/test/connectivity",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def test_vless(
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
        response = await self.client.post(
            f"{self.base_url}/orchestrator/test/vless",
            json=payload,
            timeout=timeout + 15
        )
        response.raise_for_status()
        return response.json()

    async def parse_subscription(self, subscription_url: str) -> List[str]:
        """Fetch and parse a VLESS subscription"""
        response = await self.client.get(subscription_url)
        response.raise_for_status()
        decoded = base64.b64decode(response.text).decode('utf-8')
        return [line.strip() for line in decoded.split('\n') if line.strip()]

    async def test_subscription_links_parallel(
        self,
        subscription_url: str,
        max_links: Optional[int] = None,
        timeout: int = 20,
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Test multiple VLESS links in parallel with concurrency limit

        Args:
            subscription_url: URL of the subscription
            max_links: Maximum number of links to test
            timeout: Timeout per link
            max_concurrent: Maximum concurrent tests
        """
        links = await self.parse_subscription(subscription_url)

        if max_links:
            links = links[:max_links]

        semaphore = asyncio.Semaphore(max_concurrent)

        async def test_link(index: int, vless_url: str):
            async with semaphore:
                print(f"Testing link {index + 1}/{len(links)}...")
                try:
                    result = await self.test_vless(vless_url, timeout=timeout)
                    return {
                        'link_index': index + 1,
                        'vless_url': vless_url[:80] + '...' if len(vless_url) > 80 else vless_url,
                        'result': result
                    }
                except Exception as e:
                    import traceback
                    error_details = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                    return {
                        'link_index': index + 1,
                        'vless_url': vless_url[:80] + '...' if len(vless_url) > 80 else vless_url,
                        'error': error_details if str(e) else error_details
                    }

        tasks = [test_link(i, link) for i, link in enumerate(links)]
        results = await asyncio.gather(*tasks)
        return results
