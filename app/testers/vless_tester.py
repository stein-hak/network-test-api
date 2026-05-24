"""
VLESS Tester - Wrapper for /home/stein/python/vless-tester
"""

import sys
import os
import logging
import urllib.parse
import time
from typing import Dict, Optional
from pathlib import Path

# Add vless-tester submodule to path
project_root = Path(__file__).parent.parent.parent
vless_tester_path = project_root / 'vless-tester'
sys.path.insert(0, str(vless_tester_path))

try:
    from vless_tester import VLESSTester as VlessTesterCore, parse_vless_link, VLESSConfig
except ImportError as e:
    logger.error(f"Failed to import vless_tester: {e}")
    VlessTesterCore = None
    parse_vless_link = None
    VLESSConfig = None

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
            raise ImportError("VLESS tester not available. Check /app/vless-tester is present")

        self.xray_binary = xray_binary
        # Initialize the core tester - will be used per request
        self.core_tester = VlessTesterCore(xray_path=xray_binary, quiet=True)

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
            timeout: Timeout in seconds (not used, kept for API compatibility)
            test_url: URL to fetch through proxy for verification (not used, kept for API compatibility)

        Returns:
            Dict with success, remark, latency_ms, error
        """
        result = {
            "success": False,
            "remark": "Unknown",
            "latency_ms": None,
            "error": None
        }

        # Extract remark from URL first (for display even if parsing fails)
        if "#" in vless_url:
            result["remark"] = urllib.parse.unquote(vless_url.split("#")[-1])

        try:
            # Parse the VLESS URL into a VLESSConfig object
            logger.info(f"Parsing VLESS URL: {vless_url[:50]}...")
            vless_config = parse_vless_link(vless_url)

            if vless_config is None:
                result["error"] = "Failed to parse VLESS URL"
                logger.error(f"parse_vless_link returned None for URL: {vless_url[:100]}")
                return result

            # Verify it's a VLESSConfig dataclass
            if not isinstance(vless_config, type(vless_config)) or not hasattr(vless_config, 'name'):
                result["error"] = f"Invalid config type: {type(vless_config).__name__}"
                logger.error(f"Wrong type from parse_vless_link: {type(vless_config)}")
                return result

            # Update remark from parsed config
            result["remark"] = vless_config.name
            logger.info(f"Parsed config for: {vless_config.name}")

            # Test the connection using vless-tester's test_connection method
            logger.info(f"Testing connection to {vless_config.address}:{vless_config.port}...")
            start_time = time.time()

            # test_connection returns dict with: name, address, port, success, original_ip, proxy_ip, ip_changed, error
            test_result = self.core_tester.test_connection(vless_config)

            latency_ms = (time.time() - start_time) * 1000
            logger.info(f"Test completed in {latency_ms:.2f}ms - Success: {test_result.get('success', False)}")

            # Map the test result to our API format
            result["success"] = test_result.get("success", False)
            result["latency_ms"] = round(latency_ms, 2) if result["success"] else None
            result["error"] = test_result.get("error")

            # Log IP change if successful
            if result["success"]:
                original_ip = test_result.get("original_ip")
                proxy_ip = test_result.get("proxy_ip")
                logger.info(f"IP changed: {original_ip} -> {proxy_ip}")

            return result

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"VLESS test exception: {e}\n{error_trace}")
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
            except Exception as e:
                logger.error(f"Error stopping xray: {e}")
