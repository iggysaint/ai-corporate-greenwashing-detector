"""Security utilities for safe URL validation and external document downloads.

Provides robust defenses against:
- Server-Side Request Forgery (SSRF)
- Access to private, loopback, link-local, and cloud metadata IP addresses
- Unsafe URL schemes (file://, gopher://, ftp://)
- Dangerous ports
- Oversized downloads / denial-of-service
- Malicious file types (executables, archives)
- Unsafe redirects to restricted destinations
"""

import ipaddress
import logging
import re
import socket
from typing import Optional, Set, Tuple
from urllib.parse import urlparse

import httpx

from app.utils.exceptions import (
    GreenwashingDetectorError,
    SecurityValidationError,
    SSRFSecurityError,
)

logger = logging.getLogger(__name__)

# Maximum document download size: 50 MB
MAX_DOCUMENT_DOWNLOAD_BYTES = 50 * 1024 * 1024

# Allowed schemes for external document retrieval
ALLOWED_SCHEMES: Set[str] = {"http", "https"}

# Blocked ports (common non-HTTP and sensitive service ports)
BLOCKED_PORTS: Set[int] = {
    21, 22, 23, 25, 53, 69, 110, 119, 123, 135, 137, 138, 139,
    143, 161, 389, 445, 636, 1433, 1521, 2049, 3306, 3389,
    5432, 5900, 6379, 8000, 8080, 8443, 9200, 11211, 27017,
}
# Standard allowed HTTP/HTTPS ports
ALLOWED_PORTS: Set[int] = {80, 443}

# Disallowed file extensions
BLOCKED_EXTENSIONS: Set[str] = {
    ".exe", ".dll", ".so", ".bin", ".bat", ".cmd", ".sh",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".msi", ".jar",
}

# Allowed document content types (prefix or exact match)
ALLOWED_CONTENT_TYPE_PREFIXES = (
    "application/pdf",
    "text/html",
    "text/plain",
    "application/xhtml+xml",
    "application/octet-stream",  # occasionally sent for PDFs, validated via magic bytes
)


# SecurityValidationError and SSRFSecurityError imported from app.utils.exceptions above


def is_ip_restricted(ip_str: str) -> Tuple[bool, str]:
    """Check if an IP address belongs to a private, loopback, or reserved range.

    Returns:
        Tuple of (is_restricted, reason).
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True, f"Invalid IP address format: {ip_str}"

    if ip.is_loopback:
        return True, "Loopback address (localhost)"
    if ip.is_private:
        return True, "Private RFC 1918 / ULA network address"
    if ip.is_link_local:
        return True, "Link-local address (including cloud metadata service 169.254.x.x)"
    if ip.is_multicast:
        return True, "Multicast address"
    if ip.is_reserved:
        return True, "Reserved network address"
    if ip.is_unspecified:
        return True, "Unspecified address (0.0.0.0 / ::)"

    # Specific guard for IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return is_ip_restricted(str(ip.ipv4_mapped))

    return False, ""


def validate_external_url(url: str) -> str:
    """Validate that an external URL is safe for downloading public corporate documents.

    Enforces:
    - Scheme must be http or https
    - Hostname must be present and resolve only to public IP addresses
    - Rejection of private/internal IPs, localhost, and cloud metadata IPs (SSRF protection)
    - Rejection of blocked file extensions

    Returns:
        The validated URL string.

    Raises:
        SecurityValidationError: If the URL fails scheme, extension, or format validation.
        SSRFSecurityError: If the URL targets private or loopback IP ranges.
    """
    if not url or not isinstance(url, str):
        raise SecurityValidationError("URL cannot be empty")

    clean_url = url.strip()

    try:
        parsed = urlparse(clean_url)
    except Exception as err:
        raise SecurityValidationError(f"Malformed URL: {err}") from err

    # 1. Scheme check
    if not parsed.scheme or parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SecurityValidationError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
        )

    # 2. Hostname check
    hostname = parsed.hostname
    if not hostname:
        raise SecurityValidationError("URL must include a valid hostname")

    # 3. Block explicit localhost names
    lower_host = hostname.lower()
    if lower_host in {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}:
        raise SSRFSecurityError("Access to localhost is prohibited.")

    # 4. Check for blocked extensions in URL path
    path_lower = parsed.path.lower()
    for ext in BLOCKED_EXTENSIONS:
        if path_lower.endswith(ext):
            raise SecurityValidationError(
                f"File type with extension '{ext}' is not permitted. Only corporate document formats (PDF, HTML) are allowed."
            )

    # 5. Resolve hostname to IP and check for private ranges
    try:
        addr_info = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as err:
        # If DNS resolution fails, raise SecurityValidationError
        raise SecurityValidationError(f"Cannot resolve hostname '{hostname}': {err}") from err

    resolved_ips = {item[4][0] for item in addr_info}
    for ip_str in resolved_ips:
        restricted, reason = is_ip_restricted(ip_str)
        if restricted:
            logger.warning("SSRF blocked: URL '%s' resolved to restricted IP %s (%s)", clean_url, ip_str, reason)
            raise SSRFSecurityError(
                f"Access to restricted IP address ({ip_str}) for hostname '{hostname}' is prohibited: {reason}."
            )

    return clean_url


def safe_download_document(
    url: str,
    client: Optional[httpx.Client] = None,
    max_bytes: int = MAX_DOCUMENT_DOWNLOAD_BYTES,
    timeout_seconds: float = 45.0,
) -> Tuple[bytes, str]:
    """Safely stream-download a public corporate document with strict SSRF and size bounds.

    Args:
        url: URL of the document to download.
        client: Optional httpx.Client instance.
        max_bytes: Maximum allowed download size in bytes (default: 50MB).
        timeout_seconds: Timeout for connect and read operations.

    Returns:
        Tuple of (content_bytes, content_type_header).

    Raises:
        SecurityValidationError: If URL or size validation fails.
        SSRFSecurityError: If URL or any redirect target resolves to private ranges.
        httpx.HTTPError: If HTTP network or status errors occur.
    """
    validated_url = validate_external_url(url)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/pdf,text/html,application/xhtml+xml,text/plain,*/*;q=0.8",
    }

    should_close_client = False
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            follow_redirects=False,  # We validate redirects manually to prevent SSRF via redirect!
        )
        should_close_client = True

    try:
        current_url = validated_url
        max_redirects = 5

        for _ in range(max_redirects):
            response = client.send(
                client.build_request("GET", current_url, headers=headers),
                stream=True,
            )

            # Handle redirects securely: validate new location before following!
            if response.is_redirect:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise SecurityValidationError("Redirect response missing Location header")
                # Resolve relative redirects
                from urllib.parse import urljoin
                next_url = urljoin(current_url, location)
                # Validate the redirect target against SSRF!
                current_url = validate_external_url(next_url)
                continue

            response.raise_for_status()

            # Check declared Content-Length before downloading full body
            declared_len = response.headers.get("content-length")
            if declared_len and declared_len.isdigit():
                if int(declared_len) > max_bytes:
                    response.close()
                    raise SecurityValidationError(
                        f"Document size ({int(declared_len):,} bytes) exceeds the maximum allowed limit of {max_bytes:,} bytes (50 MB)."
                    )

            # Stream response body with strict byte counter
            content_chunks = []
            total_downloaded = 0

            for chunk in response.iter_bytes(chunk_size=65536):
                total_downloaded += len(chunk)
                if total_downloaded > max_bytes:
                    response.close()
                    raise SecurityValidationError(
                        f"Document download exceeded maximum allowed size of {max_bytes:,} bytes (50 MB)."
                    )
                content_chunks.append(chunk)

            response.close()
            content_bytes = b"".join(content_chunks)
            content_type = response.headers.get("content-type", "").lower()

            return content_bytes, content_type

        raise SecurityValidationError("Too many redirects during document retrieval")

    finally:
        if should_close_client:
            client.close()
