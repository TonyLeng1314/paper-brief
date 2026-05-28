"""Fetch arxiv PDFs, extract text, cache to disk.

Used by the stage-2 deep-annotation pass. Pure text extraction via pypdf —
no OCR, no vision multimodal. Caches forever at cache/pdf_text/{arxiv_id}.txt;
manually `rm -rf cache/` to refresh.
"""
from __future__ import annotations

import io
import logging
import re
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}"
USER_AGENT = "paper-brief/1.0 (https://github.com/)"
MAX_TEXT_CHARS = 60_000  # ~15k token, leaves headroom for the deep prompt
REQUEST_TIMEOUT = 60
INTER_FETCH_DELAY_S = 3.0


def _safe_id(arxiv_id: str) -> str:
    """arxiv ids look like '2605.25313' or '2605.25313v2'. Strip version, sanitize."""
    base = arxiv_id.split("v")[0]
    return re.sub(r"[^a-zA-Z0-9._-]", "_", base)


def _extract_text(pdf_bytes: bytes) -> str:
    """Pure-Python pypdf text extraction. Returns '' on any failure."""
    try:
        from pypdf import PdfReader  # imported lazily so test paths don't need pypdf
    except ImportError:
        log.error("pypdf not installed; run `pip install pypdf>=4.0`")
        return ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception as e:
                log.warning("pypdf page extract failed: %s", e)
        text = "\n".join(parts)
    except Exception as e:
        log.warning("pypdf reader failed: %s", e)
        return ""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_pdf_text(arxiv_id: str, cache_dir: Path) -> str:
    """Download arxiv PDF, extract text, cache. Returns '' on failure.

    Cache hits skip both download and extraction.
    """
    if not arxiv_id:
        return ""
    safe = _safe_id(arxiv_id)
    cache_file = cache_dir / "pdf_text" / f"{safe}.txt"
    if cache_file.exists():
        try:
            return cache_file.read_text(encoding="utf-8")
        except Exception as e:
            log.warning("cache read failed for %s: %s", arxiv_id, e)

    url = ARXIV_PDF_URL.format(arxiv_id=arxiv_id)
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:
        log.warning("PDF download failed for %s: %s", arxiv_id, e)
        return ""

    text = _extract_text(resp.content)
    if not text:
        log.warning("Empty extraction for %s (%d bytes PDF)", arxiv_id, len(resp.content))
        return ""

    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text, encoding="utf-8")
    except Exception as e:
        log.warning("cache write failed for %s: %s", arxiv_id, e)

    time.sleep(INTER_FETCH_DELAY_S)
    return text
