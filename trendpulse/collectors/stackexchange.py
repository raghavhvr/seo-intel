from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from trendpulse.collectors.base import Collector, http_get, today
from trendpulse.keywords import normalize, valid_candidate
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

API = "https://api.stackexchange.com/2.3"


class StackExchangeCollector(Collector):
    """Official Stack Exchange API (free, 10k requests/day with no key).
    Question volume per keyword + hot question titles — prime AEO material,
    since these are literally the questions people want answered."""

    name = "stackexchange"

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        sites = self.cfg.get("stackexchange", {}).get("sites", ["webmasters"])
        week_ago = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
        obs: list[Observation] = []
        discs: list[Discovery] = []

        for site in sites:
            for kw in keywords[:60]:
                try:
                    resp = http_get(f"{API}/search", params={
                        "site": site, "intitle": kw, "fromdate": week_ago,
                        "filter": "total",
                    }, timeout=15, retries=1)
                    total = float(resp.json().get("total", 0))
                    obs.append(Observation(
                        date=date, keyword=kw, source=self.name,
                        metric=f"questions_7d_{site}", value=total,
                    ))
                except Exception as exc:  # noqa: BLE001
                    log.debug("[%s] %s '%s' failed: %s", self.name, site, kw, exc)
                time.sleep(0.15)

            try:
                resp = http_get(f"{API}/questions", params={
                    "site": site, "order": "desc", "sort": "hot", "pagesize": 40,
                }, timeout=15, retries=1)
                for item in resp.json().get("items", []):
                    title = normalize(item.get("title") or "")
                    if valid_candidate(title):
                        discs.append(Discovery(
                            date=date, keyword=title, source=self.name,
                            context=f"hot question on {site}: {item.get('link', '')}",
                            score=float(item.get("score", 0)) + float(item.get("answer_count", 0)),
                        ))
            except Exception as exc:  # noqa: BLE001
                log.debug("[%s] %s hot failed: %s", self.name, site, exc)
        return obs, discs
