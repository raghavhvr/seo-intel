from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from trendpulse.collectors.base import Collector, http_get
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)


class WikipediaCollector(Collector):
    """Wikimedia Pageviews API (official, open data, daily updates), one
    Wikipedia edition per configured language (e.g. en + ar for the Gulf).
    Resolves each keyword to its closest article, then backfills ~60 days of
    daily pageviews — instant training history on first run. Pageviews are
    global per edition (the API has no country filter)."""

    name = "wikipedia"

    def _resolve_title(self, project: str, keyword: str) -> str | None:
        resp = http_get(f"https://{project}/w/api.php", params={
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
        languages = self.cfg.get("languages") or ["en"]

        for lang in languages:
            project = f"{lang}.wikipedia.org"
            for kw in keywords:
                try:
                    title = self._resolve_title(project, kw)
                    if not title:
                        continue
                    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/"
                           f"per-article/{project}/all-access/all-agents/"
                           f"{title.replace(' ', '_')}/daily/{rng}")
                    resp = http_get(url, timeout=15, retries=1)
                    for item in resp.json().get("items", []):
                        ts = item["timestamp"]
                        obs.append(Observation(
                            date=f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}", keyword=kw,
                            source=f"wikipedia_{lang}", metric="pageviews",
                            value=float(item["views"]), language=lang,
                            raw={"article": title},
                        ))
                except Exception as exc:  # noqa: BLE001
                    log.debug("[%s] %s '%s' failed: %s", self.name, project, kw, exc)
                time.sleep(0.1)
        return obs, []
