"""Paper sources: arxiv, HuggingFace Papers, Semantic Scholar."""
from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import re
import time
from typing import Iterable

import arxiv
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

S2_BASE = "https://api.semanticscholar.org/graph/v1"
HF_PAPERS_URL = "https://huggingface.co/papers"
USER_AGENT = "paper-brief/1.0 (https://github.com/)"


@dataclasses.dataclass
class Paper:
    title: str
    authors: list[str]
    abstract: str
    arxiv_id: str | None
    url: str
    source: str  # "arxiv" | "hf_papers" | "semantic_scholar"
    published: dt.date | None = None

    def key(self) -> str:
        """Dedup key. Prefer arxiv id, fall back to lowercased title."""
        if self.arxiv_id:
            return f"arxiv:{self.arxiv_id}"
        return f"title:{re.sub(r'[^a-z0-9]+', '', self.title.lower())}"


def fetch_arxiv(categories: list[str], max_per_category: int = 50) -> list[Paper]:
    """Pull the latest preprints from each arxiv category."""
    out: list[Paper] = []
    client = arxiv.Client(page_size=max_per_category, delay_seconds=3, num_retries=3)
    for cat in categories:
        search = arxiv.Search(
            query=f"cat:{cat}",
            max_results=max_per_category,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        try:
            for r in client.results(search):
                aid = r.get_short_id().split("v")[0]
                out.append(
                    Paper(
                        title=r.title.strip().replace("\n", " "),
                        authors=[a.name for a in r.authors],
                        abstract=r.summary.strip().replace("\n", " "),
                        arxiv_id=aid,
                        url=r.entry_id,
                        source="arxiv",
                        published=r.published.date() if r.published else None,
                    )
                )
        except Exception as e:
            log.warning("arxiv fetch failed for %s: %s", cat, e)
    return out


def fetch_huggingface_papers(date: dt.date | None = None) -> list[Paper]:
    """Scrape HuggingFace Papers daily list. Returns the day's curated set."""
    url = HF_PAPERS_URL
    if date:
        url = f"{HF_PAPERS_URL}?date={date.isoformat()}"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        log.warning("HF Papers fetch failed: %s", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    out: list[Paper] = []
    for a in soup.select('a[href^="/papers/"]'):
        href = a.get("href", "")
        m = re.match(r"^/papers/(\d{4}\.\d{4,5})", href)
        if not m:
            continue
        aid = m.group(1)
        title = a.get_text(strip=True)
        if not title or len(title) < 8:
            continue
        if any(p.arxiv_id == aid for p in out):
            continue
        out.append(
            Paper(
                title=title,
                authors=[],
                abstract="",
                arxiv_id=aid,
                url=f"https://arxiv.org/abs/{aid}",
                source="hf_papers",
                published=date,
            )
        )
    return out


def _s2_get(path: str, params: dict | None = None) -> dict | None:
    """Hit S2 graph API with light retry on 429."""
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(3):
        try:
            r = requests.get(f"{S2_BASE}{path}", params=params, headers=headers, timeout=20)
            if r.status_code == 429:
                time.sleep(2 + attempt * 3)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning("S2 %s attempt %d failed: %s", path, attempt, e)
            time.sleep(1 + attempt)
    return None


def fetch_semantic_scholar_authors(
    author_names: Iterable[str], lookback_days: int = 7
) -> list[Paper]:
    """For each tracked author, return their new papers within lookback window."""
    cutoff = dt.date.today() - dt.timedelta(days=lookback_days)
    out: list[Paper] = []
    for name in author_names:
        data = _s2_get("/author/search", {"query": name, "limit": 3})
        if not data or not data.get("data"):
            continue
        # Match the top hit; S2 search is decent enough for famous authors.
        author_id = data["data"][0]["authorId"]
        papers_data = _s2_get(
            f"/author/{author_id}/papers",
            {
                "limit": 20,
                "fields": "title,abstract,authors,externalIds,publicationDate,url",
            },
        )
        if not papers_data:
            continue
        for p in papers_data.get("data", []):
            pub = p.get("publicationDate")
            pub_date = None
            if pub:
                try:
                    pub_date = dt.date.fromisoformat(pub)
                except ValueError:
                    pub_date = None
            if pub_date and pub_date < cutoff:
                continue
            ext = p.get("externalIds") or {}
            aid = ext.get("ArXiv")
            url = p.get("url") or (f"https://arxiv.org/abs/{aid}" if aid else "")
            out.append(
                Paper(
                    title=(p.get("title") or "").strip(),
                    authors=[a.get("name", "") for a in p.get("authors") or []],
                    abstract=(p.get("abstract") or "").strip(),
                    arxiv_id=aid,
                    url=url,
                    source="semantic_scholar",
                    published=pub_date,
                )
            )
        time.sleep(0.5)  # be polite
    return out


def enrich_arxiv_metadata(papers: list[Paper]) -> None:
    """For HF papers that came in without abstract, pull abstract from arxiv."""
    missing = [p for p in papers if p.arxiv_id and not p.abstract]
    if not missing:
        return
    ids = [p.arxiv_id for p in missing]
    client = arxiv.Client(page_size=min(50, len(ids)), delay_seconds=3, num_retries=2)
    search = arxiv.Search(id_list=ids)
    by_id: dict[str, arxiv.Result] = {}
    try:
        for r in client.results(search):
            by_id[r.get_short_id().split("v")[0]] = r
    except Exception as e:
        log.warning("arxiv enrich failed: %s", e)
        return
    for p in missing:
        r = by_id.get(p.arxiv_id)
        if not r:
            continue
        if not p.abstract:
            p.abstract = r.summary.strip().replace("\n", " ")
        if not p.authors:
            p.authors = [a.name for a in r.authors]
        if not p.published:
            p.published = r.published.date() if r.published else None
        if not p.title:
            p.title = r.title.strip().replace("\n", " ")


def dedupe(papers: list[Paper]) -> list[Paper]:
    seen: dict[str, Paper] = {}
    source_priority = {"hf_papers": 0, "semantic_scholar": 1, "arxiv": 2}
    for p in papers:
        k = p.key()
        if k not in seen:
            seen[k] = p
            continue
        # If we already have it, keep the version with the richer abstract,
        # tiebreak by source priority (HF curated > S2 > arxiv firehose).
        existing = seen[k]
        if len(p.abstract) > len(existing.abstract):
            seen[k] = p
        elif source_priority.get(p.source, 99) < source_priority.get(existing.source, 99):
            seen[k] = p
    return list(seen.values())
