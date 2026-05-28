"""
Virus scanning for uploaded files.

Uses ClamAV (via pyclamd) when available, otherwise falls back to a no-op.
Set ENABLE_VIRUS_SCAN=true in .env to activate.
Set CLAMAV_HOST and CLAMAV_PORT if ClamAV runs on a remote host.

Usage:
    from modules.virus_scanner import scan_file
    result = scan_file("/path/to/uploaded/file.mp3")
    if not result["safe"]:
        # reject the file
"""

import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("ENABLE_VIRUS_SCAN", "false").strip().lower() == "true"
_CLAMAV_HOST = os.getenv("CLAMAV_HOST", "localhost")
_CLAMAV_PORT = int(os.getenv("CLAMAV_PORT", "3310"))

_scanner = None
_scanner_initialized = False


def _get_scanner():
    """Lazy-init ClamAV connection."""
    global _scanner, _scanner_initialized
    if _scanner_initialized:
        return _scanner
    _scanner_initialized = True

    if not _ENABLED:
        logger.info("Virus scanning disabled (ENABLE_VIRUS_SCAN=false)")
        return None

    try:
        import pyclamd
        cd = pyclamd.ClamdNetworkSocket(host=_CLAMAV_HOST, port=_CLAMAV_PORT, timeout=30)
        if cd.ping():
            _scanner = cd
            logger.info(f"ClamAV connected at {_CLAMAV_HOST}:{_CLAMAV_PORT}")
        else:
            logger.warning("ClamAV ping failed — virus scanning disabled")
    except ImportError:
        logger.warning("pyclamd not installed — virus scanning disabled. Install with: pip install pyclamd")
    except Exception as e:
        logger.warning(f"ClamAV connection failed: {e} — virus scanning disabled")

    return _scanner


def scan_file(filepath: str) -> Dict[str, Any]:
    """
    Scan a file for viruses.

    Returns:
        {
            "safe": bool,       # True if file is clean or scanning is disabled
            "scanned": bool,    # True if scan was actually performed
            "threat": str|None, # Name of detected threat, or None
        }
    """
    scanner = _get_scanner()

    if scanner is None:
        return {"safe": True, "scanned": False, "threat": None}

    try:
        result = scanner.scan_file(filepath)
        if result is None:
            # No threat found
            logger.debug(f"Virus scan clean: {os.path.basename(filepath)}")
            return {"safe": True, "scanned": True, "threat": None}
        else:
            # result is like {'/path/to/file': ('FOUND', 'Eicar-Test-Signature')}
            for path, (status, threat_name) in result.items():
                if status == "FOUND":
                    logger.warning(f"VIRUS DETECTED in {os.path.basename(filepath)}: {threat_name}")
                    return {"safe": False, "scanned": True, "threat": threat_name}
            return {"safe": True, "scanned": True, "threat": None}
    except Exception as e:
        logger.error(f"Virus scan error for {os.path.basename(filepath)}: {e}")
        # Fail-open: allow the file if scanning errors out (configurable)
        fail_closed = os.getenv("VIRUS_SCAN_FAIL_CLOSED", "false").strip().lower() == "true"
        if fail_closed:
            return {"safe": False, "scanned": False, "threat": f"Scan error: {e}"}
        return {"safe": True, "scanned": False, "threat": None}
