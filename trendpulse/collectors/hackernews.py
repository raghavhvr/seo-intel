from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from trendpulse.collectors.base import Collector, http_get, today
from trendpulse.keywords import is_geo_relevant, normalize, valid_candidate
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

SEARCH_URL = "https://hn.algolia.com/api/v1/search"
FRONT_PAGE_URL = "https://hn.algolia.com/api/v1/search?tags=front_page"


class HackerNewsCollector(Collector):
    """Algolia Hacker News Search API (official, free, real-time). Mention
    counts per keyword over the trailing week + high-points stories as
    discoveries — a strong early signal for GEO/AI topics."""

    name = "hackernews"

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        week_ago = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
        obs: list[Observation] = []
        discs: list[Discovery] = []

        # HN is a global tech community — only GEO-relevant keywords have
        # signal there; tracking "credit card uae" on HN is pure noise.
        keywords = [kw for kw in keywords
                    if is_geo_relevant(kw, self.cfg.get("geo_terms"))]
        log.info("[%s] tracking %d GEO-relevant keywords", self.name, len(keywords))

        for kw in keywords:
            try:
                resp = http_get(SEARCH_URL, params={
                    "query": kw, "tags": "story",
                    "numericFilters": f"created_at_i>{week_ago}",
                }, timeout=15, retries=1)
                data = resp.json()
                obs.append(Observation(
                    date=date, keyword=kw, source=self.name,
                    metric="stories_7d", value=float(data.get("nbHits", 0)),
                ))
                for hit in data.get("hits", [])[:3]:
                    title = normalize(hit.get("title") or "")
                    if valid_candidate(title):
                        discs.append(Discovery(
                            date=date, keyword=title, source=self.name,
                            context=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                            score=float(hit.get("points") or 0),
                        ))
            except Exception as exc:  # noqa: BLE001
                log.debug("[%s] '%s' failed: %s", self.name, kw, exc)
            time.sleep(0.1)

        try:
            front = http_get(FRONT_PAGE_URL, timeout=15, retries=1).json()
            for hit in front.get("hits", [])[:30]:
                title = normalize(hit.get("title") or "")
                if valid_candidate(title):
                    discs.append(Discovery(
                        date=date, keyword=title, source=self.name,
                        context=hit.get("url") or "",
                        score=float(hit.get("points") or 0),
                    ))
        except Exception as exc:  # noqa: BLE001
            log.debug("[%s] front page failed: %s", self.name, exc)
        return obs, discs
