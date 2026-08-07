from __future__ import annotations

import logging
import time

from trendpulse.collectors.base import Collector, today
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

BATCH = 5  # Google Trends compares up to 5 terms per request


class GoogleTrendsCollector(Collector):
    """Interest-over-time backfill (last ~90 days, daily) plus rising related
    queries. Uses pytrends (unofficial API) — free, updates daily, but
    rate-limited, so failures are logged and skipped."""

    name = "google_trends"

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        from pytrends.request import TrendReq  # optional dependency

        pytrends = TrendReq(hl=self.cfg.get("language", "en-US"), tz=0, timeout=(10, 30))
        geo = self.cfg.get("region", "US")
        obs: list[Observation] = []
        discs: list[Discovery] = []
        date = today()

        for i in range(0, len(keywords), BATCH):
            batch = keywords[i:i + BATCH]
            try:
                pytrends.build_payload(batch, cat=0, timeframe="today 3-m", geo=geo)
                frame = pytrends.interest_over_time()
                if not frame.empty:
                    frame = frame.drop(columns=["isPartial"], errors="ignore")
                    for kw in batch:
                        if kw not in frame.columns:
                            continue
                        for ts, value in frame[kw].items():
                            obs.append(Observation(
                                date=ts.strftime("%Y-%m-%d"), keyword=kw,
                                source=self.name, metric="interest", value=float(value),
                            ))
                try:
                    related = pytrends.related_queries()
                except Exception:
                    related = {}
                for kw in batch:
                    rising = (related.get(kw) or {}).get("rising")
                    if rising is None or rising.empty:
                        continue
                    for _, row in rising.head(10).iterrows():
                        discs.append(Discovery(
                            date=date, keyword=str(row["query"]), source=self.name,
                            context=f"rising related query for '{kw}'",
                            score=float(row.get("value", 0)),
                        ))
            except Exception as exc:  # noqa: BLE001 - 429s are expected
                log.warning("[%s] batch %s failed: %s", self.name, batch, exc)
            time.sleep(1.5)  # be polite with the rate limiter
        return obs, discs
