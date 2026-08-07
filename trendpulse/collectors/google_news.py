from __future__ import annotations

import logging
import time
from urllib.parse import quote

import feedparser

from trendpulse.collectors.base import Collector, today
from trendpulse.keywords import normalize, valid_candidate
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

RSS_URL = "https://news.google.com/rss/search"


class GoogleNewsCollector(Collector):
    """Google News RSS (free, real-time). Article counts per keyword over the
    trailing week + headline discoveries — news velocity often leads search
    demand by a few days."""

    name = "google_news"

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        region = self.cfg.get("region", "US")
        language = self.cfg.get("language", "en-US")
        lang = language.split("-")[0]
        obs: list[Observation] = []
        discs: list[Discovery] = []

        for kw in keywords[:80]:
            url = (f"{RSS_URL}?q={quote(kw)}+when:7d&hl={language}"
                   f"&gl={region}&ceid={region}:{lang}")
            try:
                feed = feedparser.parse(url)
                entries = feed.entries or []
                obs.append(Observation(
                    date=date, keyword=kw, source=self.name,
                    metric="articles_7d", value=float(len(entries)),
                ))
                for entry in entries[:3]:
                    title = normalize(entry.get("title", "").rsplit(" - ", 1)[0])
                    if valid_candidate(title):
                        discs.append(Discovery(
                            date=date, keyword=title, source=self.name,
                            context=entry.get("link", ""),
                            score=1.0,
                        ))
            except Exception as exc:  # noqa: BLE001
                log.debug("[%s] '%s' failed: %s", self.name, kw, exc)
            time.sleep(0.2)
        return obs, discs
