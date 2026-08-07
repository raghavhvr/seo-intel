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
    """Google News RSS per country × language (free, real-time). Article
    counts per keyword over the trailing week + headline discoveries — news
    velocity often leads search demand by a few days."""

    name = "google_news"

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        regions = self.cfg.get("regions") or [self.cfg.get("region", "US")]
        languages = self.cfg.get("languages") or ["en"]
        obs: list[Observation] = []
        discs: list[Discovery] = []

        for kw in keywords[:60]:
            for region in regions[:3]:
                for lang in languages:
                    url = (f"{RSS_URL}?q={quote(kw)}+when:7d&hl={lang}"
                           f"&gl={region}&ceid={region}:{lang}")
                    try:
                        feed = feedparser.parse(url)
                        entries = feed.entries or []
                        obs.append(Observation(
                            date=date, keyword=kw, source=self.name,
                            metric="articles_7d", value=float(len(entries)),
                            region=region, language=lang,
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
                        log.debug("[%s] '%s' (%s/%s) failed: %s",
                                  self.name, kw, region, lang, exc)
                    time.sleep(0.2)
        return obs, discs
