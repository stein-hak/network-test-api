"""
Subscription Tester - Test subscription URLs and parse VLESS links
"""

import requests
import base64
import logging
from typing import Dict, List, Optional
from .vless_tester import VLESSTester

logger = logging.getLogger(__name__)


class SubscriptionTester:
    """Test subscription URLs and VLESS links"""

    def __init__(self):
        self.vless_tester = None

    def test(
        self,
        subscription_url: str,
        timeout: int = 10,
        test_links: bool = False,
        max_links: int = 3
    ) -> Dict:
        """
        Test subscription URL

        Args:
            subscription_url: Subscription URL to test
            timeout: Timeout in seconds
            test_links: Whether to test individual VLESS links
            max_links: Maximum number of links to test

        Returns:
            Dict with subscription test results
        """
        result = {
            "success": False,
            "accessible": False,
            "link_count": None,
            "tested_links": None,
            "error": None
        }

        try:
            # Fetch subscription
            response = requests.get(
                subscription_url,
                timeout=timeout,
                headers={
                    "User-Agent": "clash"  # Some subscriptions require specific UA
                }
            )

            if response.status_code != 200:
                result["error"] = f"HTTP {response.status_code}"
                return result

            result["accessible"] = True

            # Parse subscription content
            content = response.text.strip()

            # Try to decode if base64
            try:
                decoded = base64.b64decode(content).decode('utf-8')
                content = decoded
            except:
                # Not base64, use as-is
                pass

            # Extract VLESS links
            vless_links = self._extract_vless_links(content)
            result["link_count"] = len(vless_links)

            logger.info(f"Found {len(vless_links)} VLESS links in subscription")

            # Test links if requested
            if test_links and vless_links:
                if self.vless_tester is None:
                    self.vless_tester = VLESSTester()

                links_to_test = vless_links[:max_links]
                tested = []

                for link in links_to_test:
                    test_result = self.vless_tester.test(link, timeout=15)
                    tested.append(test_result)

                result["tested_links"] = tested

            result["success"] = True

        except requests.exceptions.Timeout:
            result["error"] = f"Request timeout after {timeout}s"
        except requests.exceptions.SSLError as e:
            result["error"] = f"SSL error: {str(e)[:100]}"
        except requests.exceptions.ConnectionError as e:
            result["error"] = f"Connection error: {str(e)[:100]}"
        except Exception as e:
            logger.error(f"Subscription test failed: {e}")
            result["error"] = str(e)[:200]

        return result

    def _extract_vless_links(self, content: str) -> List[str]:
        """
        Extract VLESS links from subscription content

        Args:
            content: Subscription content (plain text or decoded)

        Returns:
            List of VLESS URLs
        """
        vless_links = []

        # Split by newlines
        lines = content.split('\n')

        for line in lines:
            line = line.strip()
            if line.startswith('vless://'):
                vless_links.append(line)

        return vless_links

    def parse_subscription(self, subscription_url: str, timeout: int = 10) -> Optional[List[str]]:
        """
        Parse subscription and return VLESS links

        Args:
            subscription_url: Subscription URL
            timeout: Timeout in seconds

        Returns:
            List of VLESS URLs, None on error
        """
        try:
            response = requests.get(subscription_url, timeout=timeout)

            if response.status_code != 200:
                return None

            content = response.text.strip()

            # Try to decode if base64
            try:
                decoded = base64.b64decode(content).decode('utf-8')
                content = decoded
            except:
                pass

            return self._extract_vless_links(content)

        except Exception as e:
            logger.error(f"Failed to parse subscription: {e}")
            return None
