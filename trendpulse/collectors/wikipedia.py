from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from trendpulse.collectors.base import Collector, http_get
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

SEARCH_URL = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"


class WikipediaCollector(Collector):
    """Wikimedia Pageviews API (official, open data, daily updates). Resolves
    each keyword to its closest Wikipedia article, then backfills ~60 days of
    daily pageviews — instant training history on first run."""

    name = "wikipedia"

    def _resolve_title(self, keyword: str) -> str | None:
        resp = http_get(SEARCH_URL, params={
            "action": "query", "list": "search", "srsearch": keyword,
            "format": "json", "srlimit": 1,
        }, timeout=15, retries=1)
        results = resp.json().get("query", {}).get("search", [])
        return results[0]["title"] if results else None

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        obs: list[Observation] = []
        end = datetime.now(timezone.utc) - timedelta(days=1)
        start = end - timedelta(days=60)
        rng = f"{start:%Y%m%d}00/{end:%Y%m%d}00"

        for kw in keywords:
            try:
                title = self._resolve_title(kw)
                if not title:
                    continue
                url = (f"{PAGEVIEWS_URL}/en.wikipedia/all-access/all-agents/"
                       f"{title.replace(' ', '_')}/daily/{rng}")
                resp = http_get(url, timeout=15, retries=1)
                for item in resp.json().get("items", []):
                    ts = item["timestamp"]
                    obs.append(Observation(
                        date=f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}", keyword=kw,
                        source=self.name, metric="pageviews",
                        value=float(item["views"]),
                        raw={"article": title},
                    ))
            except Exception as exc:  # noqa: BLE001
                log.debug("[%s] '%s' failed: %s", self.name, kw, exc)
            time.sleep(0.1)
        return obs, []
