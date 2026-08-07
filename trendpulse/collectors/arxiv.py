from __future__ import annotations

import logging
import time
from urllib.parse import quote

import feedparser

from trendpulse.collectors.base import Collector, today
from trendpulse.keywords import normalize, valid_candidate
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

API_URL = "https://export.arxiv.org/api/query"


class ArxivCollector(Collector):
    """arXiv API (official, open). New-paper velocity per keyword is a leading
    indicator for GEO: research chatter turns into AI-assistant answers weeks
    to months later."""

    name = "arxiv"

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        obs: list[Observation] = []
        discs: list[Discovery] = []

        for kw in keywords[:40]:
            query = quote(f'all:"{kw}"')
            url = (f"{API_URL}?search_query={query}&sortBy=submittedDate"
                   f"&sortOrder=descending&start=0&max_results=15")
            try:
                feed = feedparser.parse(url)
                entries = feed.entries or []
                obs.append(Observation(
                    date=date, keyword=kw, source=self.name,
                    metric="recent_papers", value=float(len(entries)),
                ))
                for entry in entries[:2]:
                    title = normalize(entry.get("title", "").replace("\n", " "))
                    if valid_candidate(title):
                        discs.append(Discovery(
                            date=date, keyword=title, source=self.name,
                            context=entry.get("id", ""),
                            score=1.0,
                        ))
            except Exception as exc:  # noqa: BLE001
                log.debug("[%s] '%s' failed: %s", self.name, kw, exc)
            time.sleep(1.0)  # arXiv asks for <=1 request per 3s for bulk use
        return obs, discs
