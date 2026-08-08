from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from trendpulse.collectors.base import Collector, http_get, today
from trendpulse.keywords import normalize, valid_candidate
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

API = "https://api.stackexchange.com/2.3"

# Geo tokens are dropped before querying: these are global sites, and
# full-phrase intitle matching ("credit card uae") returns zero while the
# core product terms ("credit card") have real volume. A 30-day window is
# used because post-2024 question cadence on these sites is low — a 7-day
# window is almost always empty.
GEO_TOKENS = {"uae", "emirates", "dubai", "abu", "dhabi", "abudhabi", "saudi",
              "arabia", "gcc", "mena", "qatar", "kuwait", "bahrain", "oman",
              "jordan", "lebanon", "mena", "الإمارات", "دبي"}


def _core_terms(keyword: str) -> str:
    terms = [t for t in keyword.split() if t not in GEO_TOKENS]
    return " ".join(terms) if terms else keyword


class StackExchangeCollector(Collector):
    """Official Stack Exchange API (free, 10k requests/day with no key).
    Question volume per keyword + hot question titles — prime AEO material,
    since these are literally the questions people want answered."""

    name = "stackexchange"

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        sites = self.cfg.get("stackexchange", {}).get("sites", ["webmasters"])
        month_ago = int((datetime.now(timezone.utc) - timedelta(days=30)).timestamp())
        obs: list[Observation] = []
        discs: list[Discovery] = []

        for site in sites:
            for kw in keywords[:60]:
                try:
                    resp = http_get(f"{API}/search", params={
                        "site": site, "intitle": _core_terms(kw),
                        "fromdate": month_ago, "filter": "total",
                    }, timeout=15, retries=1)
                    total = float(resp.json().get("total", 0))
                    obs.append(Observation(
                        date=date, keyword=kw, source=self.name,
                        metric=f"questions_30d_{site}", value=total,
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
