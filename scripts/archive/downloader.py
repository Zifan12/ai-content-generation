"""
Single-file media downloader. Streams a URL to disk, returns ok/fail.

Best-effort by contract: any HTTP error, non-2xx status, or OS error yields
False (and no partial file left behind) rather than raising. The caller
decides whether a given file is critical and how to log the miss.
"""

from pathlib import Path

import httpx

DEFAULT_TIMEOUT = 60.0


def download(url: str, target: Path, timeout: float = DEFAULT_TIMEOUT) -> bool:
    """
    Stream the content at url into target. Return True iff fully written.

    Creates parent directories. On any failure (non-2xx, network error, OS
    error) returns False and removes any partial file. Does not raise.

    Args:
        url: source URL (signed TikTok CDN link).
        target: destination path; parents created if missing.
        timeout: per-request timeout in seconds.

    Returns:
        True on success, False on any failure.
    """
    target = Path(target)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as resp:
            resp.raise_for_status()
            with target.open("wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
        return True
    except (httpx.HTTPError, OSError):
        if target.exists():
            try:
                target.unlink()
            except OSError:
                pass
        return False
