"""
Connectivity Tester - Test domain/IP connectivity
"""

import socket
import time
import requests
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ConnectivityTester:
    """Test connectivity to domains and IP addresses"""

    def test(
        self,
        target: str,
        port: int = 443,
        timeout: int = 10,
        protocol: str = "tcp"
    ) -> Dict:
        """
        Test connectivity to target

        Args:
            target: Domain or IP address
            port: Port number
            timeout: Timeout in seconds
            protocol: Protocol (tcp, udp, http, https)

        Returns:
            Dict with success, latency_ms, error
        """
        result = {
            "success": False,
            "latency_ms": None,
            "error": None
        }

        try:
            if protocol == "tcp":
                return self._test_tcp(target, port, timeout)
            elif protocol == "udp":
                return self._test_udp(target, port, timeout)
            elif protocol in ["http", "https"]:
                return self._test_http(target, port, timeout, protocol)
            else:
                result["error"] = f"Unsupported protocol: {protocol}"
                return result

        except Exception as e:
            logger.error(f"Connectivity test failed: {e}")
            result["error"] = str(e)
            return result

    def _test_tcp(self, target: str, port: int, timeout: int) -> Dict:
        """Test TCP connectivity"""
        result = {
            "success": False,
            "latency_ms": None,
            "error": None
        }

        try:
            start_time = time.time()

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)

            sock.connect((target, port))

            latency = (time.time() - start_time) * 1000
            result["success"] = True
            result["latency_ms"] = round(latency, 2)

            sock.close()

        except socket.timeout:
            result["error"] = f"Connection timeout after {timeout}s"
        except socket.gaierror as e:
            result["error"] = f"DNS resolution failed: {e}"
        except ConnectionRefusedError:
            result["error"] = "Connection refused"
        except Exception as e:
            result["error"] = str(e)

        return result

    def _test_udp(self, target: str, port: int, timeout: int) -> Dict:
        """Test UDP connectivity (note: UDP is connectionless, limited test)"""
        result = {
            "success": False,
            "latency_ms": None,
            "error": None
        }

        try:
            start_time = time.time()

            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)

            # Send a test packet
            sock.sendto(b"test", (target, port))

            # Try to receive (may timeout - that's ok for UDP)
            try:
                sock.recvfrom(1024)
            except socket.timeout:
                # Timeout is expected for UDP if server doesn't respond
                pass

            latency = (time.time() - start_time) * 1000
            result["success"] = True
            result["latency_ms"] = round(latency, 2)

            sock.close()

        except socket.gaierror as e:
            result["error"] = f"DNS resolution failed: {e}"
        except Exception as e:
            result["error"] = str(e)

        return result

    def _test_http(self, target: str, port: int, timeout: int, protocol: str) -> Dict:
        """Test HTTP/HTTPS connectivity"""
        result = {
            "success": False,
            "latency_ms": None,
            "error": None
        }

        try:
            # Build URL
            if port == 80 and protocol == "http":
                url = f"http://{target}/"
            elif port == 443 and protocol == "https":
                url = f"https://{target}/"
            else:
                url = f"{protocol}://{target}:{port}/"

            start_time = time.time()

            response = requests.get(
                url,
                timeout=timeout,
                allow_redirects=True,
                verify=True  # Verify SSL certificates
            )

            latency = (time.time() - start_time) * 1000

            # Consider 2xx and 3xx as success
            if 200 <= response.status_code < 400:
                result["success"] = True
                result["latency_ms"] = round(latency, 2)
            else:
                result["error"] = f"HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            result["error"] = f"HTTP timeout after {timeout}s"
        except requests.exceptions.SSLError as e:
            result["error"] = f"SSL error: {str(e)[:100]}"
        except requests.exceptions.ConnectionError as e:
            result["error"] = f"Connection error: {str(e)[:100]}"
        except Exception as e:
            result["error"] = str(e)[:100]

        return result
