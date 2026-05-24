"""
VLESS Tester - Wrapper for /home/stein/python/vless-tester
"""

import sys
import os
import logging
from typing import Dict, Optional
from pathlib import Path

# Add vless-tester submodule to path
project_root = Path(__file__).parent.parent.parent
vless_tester_path = project_root / 'vless-tester'
sys.path.insert(0, str(vless_tester_path))

try:
    from vless_tester import XrayTester as VlessTesterCore
except ImportError:
    VlessTesterCore = None

logger = logging.getLogger(__name__)


class VLESSTester:
    """Test VLESS connections using existing vless-tester project"""

    def __init__(self, xray_binary: str = "/usr/local/bin/xray"):
        """
        Initialize VLESS tester

        Args:
            xray_binary: Path to xray binary
        """
        if VlessTesterCore is None:
            raise ImportError("VLESS tester not available. Install from /home/stein/python/vless-tester")

        self.xray_binary = xray_binary
        self.core_tester = None

    def test(
        self,
        vless_url: str,
        timeout: int = 15,
        test_url: str = "https://httpbin.org/get"
    ) -> Dict:
        """
        Test a VLESS connection

        Args:
            vless_url: VLESS URL to test
            timeout: Timeout in seconds
            test_url: URL to fetch through proxy for verification

        Returns:
            Dict with success, remark, latency_ms, error
        """
        result = {
            "success": False,
            "remark": "Unknown",
            "latency_ms": None,
            "error": None
        }

        try:
            # Initialize tester
            if self.core_tester is None:
                self.core_tester = VlessTesterCore(
                    xray_binary=self.xray_binary
                )

            # Test the VLESS URL
            test_result = self.core_tester.test_vless_url(vless_url)

            # Extract results
            result["success"] = test_result.get("success", False)
            result["remark"] = test_result.get("remark", "Unknown")
            result["latency_ms"] = test_result.get("latency_ms")
            result["error"] = test_result.get("error")

            return result

        except Exception as e:
            logger.error(f"VLESS test failed: {e}")
            result["error"] = str(e)
            return result

    def test_multiple(self, vless_urls: list, timeout: int = 15) -> list:
        """
        Test multiple VLESS URLs

        Args:
            vless_urls: List of VLESS URLs
            timeout: Timeout per test

        Returns:
            List of test results
        """
        results = []

        for url in vless_urls:
            result = self.test(url, timeout)
            results.append(result)

        return results

    def cleanup(self):
        """Cleanup resources"""
        if self.core_tester:
            try:
                self.core_tester.stop_xray()
            except:
                pass
