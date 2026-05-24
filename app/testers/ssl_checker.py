"""
SSL Certificate Checker - Verify SSL certificates
"""

import ssl
import socket
from datetime import datetime
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class SSLChecker:
    """Check SSL certificates for domains"""

    def check(
        self,
        domain: str,
        port: int = 443,
        timeout: int = 10,
        verify_chain: bool = True
    ) -> Dict:
        """
        Check SSL certificate for domain

        Args:
            domain: Domain name
            port: Port number (default: 443)
            timeout: Timeout in seconds
            verify_chain: Verify certificate chain

        Returns:
            Dict with certificate information
        """
        result = {
            "success": False,
            "valid": False,
            "issuer": None,
            "subject": None,
            "expires": None,
            "days_until_expiry": None,
            "error": None
        }

        try:
            # Create SSL context
            context = ssl.create_default_context()

            if not verify_chain:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE

            # Connect and get certificate
            with socket.create_connection((domain, port), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()

                    if not cert:
                        result["error"] = "No certificate received"
                        return result

                    # Parse certificate
                    result["success"] = True
                    result["valid"] = True

                    # Extract subject
                    subject = dict(x[0] for x in cert.get('subject', []))
                    result["subject"] = subject.get('commonName', 'Unknown')

                    # Extract issuer
                    issuer = dict(x[0] for x in cert.get('issuer', []))
                    result["issuer"] = issuer.get('commonName', 'Unknown')

                    # Parse expiration date
                    not_after = cert.get('notAfter')
                    if not_after:
                        # Format: 'Jan  1 00:00:00 2025 GMT'
                        expiry_date = datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
                        result["expires"] = expiry_date.isoformat()

                        # Calculate days until expiry
                        days_left = (expiry_date - datetime.utcnow()).days
                        result["days_until_expiry"] = days_left

                        if days_left < 0:
                            result["valid"] = False
                            result["error"] = f"Certificate expired {abs(days_left)} days ago"
                        elif days_left < 30:
                            result["error"] = f"Certificate expires in {days_left} days"

        except ssl.SSLError as e:
            result["error"] = f"SSL error: {str(e)[:200]}"
            result["valid"] = False
        except socket.timeout:
            result["error"] = f"Connection timeout after {timeout}s"
        except socket.gaierror as e:
            result["error"] = f"DNS resolution failed: {e}"
        except ConnectionRefusedError:
            result["error"] = "Connection refused"
        except Exception as e:
            logger.error(f"SSL check failed: {e}")
            result["error"] = str(e)[:200]

        return result

    def check_expiry_only(self, domain: str, port: int = 443, timeout: int = 10) -> Optional[int]:
        """
        Quick check - return days until expiry

        Returns:
            Days until expiry (negative if expired), None on error
        """
        result = self.check(domain, port, timeout)
        return result.get("days_until_expiry")
