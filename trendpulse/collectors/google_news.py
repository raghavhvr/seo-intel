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
    """Google News RSS per language (free, real-time). Article counts per
    keyword over the trailing week + headline discoveries — news velocity often
    leads search demand by a few days.

    One query per keyword × language, deliberately *not* per country. The RSS
    search endpoint is not geo-filtered: `gl`/`ceid` select the edition chrome,
    not the result set. Audited against AE/SA/QA with both `hl=en` and
    `hl=en-AE` — all six return byte-identical article sets for the same query.
    Looping over countries therefore produced three copies of one series per
    keyword, which tripled news's weight in the blended attention score and
    inflated the cross-source breadth feature. Regional intent has to come from
    the query text itself ('credit card uae'), so results carry no region tag.
    """

    name = "google_news"

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        # Only picks which Google News edition answers; the result set is the
        # same either way, so the primary market is as good as any.
        edition = (self.cfg.get("regions") or [self.cfg.get("region", "US")])[0]
        languages = self.cfg.get("languages") or ["en"]
        obs: list[Observation] = []
        discs: list[Discovery] = []

        for kw in keywords[:60]:
            for lang in languages:
                url = (f"{RSS_URL}?q={quote(kw)}+when:7d&hl={lang}"
                       f"&gl={edition}&ceid={edition}:{lang}")
                try:
                    feed = feedparser.parse(url)
                    entries = feed.entries or []
                    obs.append(Observation(
                        date=date, keyword=kw, source=self.name,
                        metric="articles_7d", value=float(len(entries)),
                        language=lang,
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
                    log.debug("[%s] '%s' (%s) failed: %s", self.name, kw, lang, exc)
                time.sleep(0.2)
        return obs, discs
