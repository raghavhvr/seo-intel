from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from trendpulse.collectors.base import Collector, today
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

BATCH = 5  # Google Trends compares up to 5 terms per request


class GoogleTrendsCollector(Collector):
    """Interest-over-time backfill (last ~90 days, daily) plus rising related
    queries, per country. Uses pytrends (unofficial API) — free and daily, but
    aggressively rate-limited: the primary region runs every day and the
    remaining regions rotate (`google_trends.regions_per_run`), with a long
    back-off + one retry on HTTP 429. Full regional coverage accrues over the
    week instead of one throttled mega-run."""

    name = "google_trends"

    def _regions_for_today(self) -> list[str]:
        regions = self.cfg.get("regions") or [self.cfg.get("region", "US")]
        per_run = int(self.cfg.get("google_trends", {}).get("regions_per_run", 4))
        if per_run >= len(regions) or len(regions) < 2:
            return regions
        primary, rest = regions[0], regions[1:]
        day = datetime.now(timezone.utc).timetuple().tm_yday
        start = (day * (per_run - 1)) % len(rest)
        rotated = rest[start:] + rest[:start]
        return [primary, *rotated[:per_run - 1]]

    def _fetch_batch(self, pytrends, batch: list[str], region: str):
        try:
            pytrends.build_payload(batch, cat=0, timeframe="today 3-m", geo=region)
            return pytrends.interest_over_time(), pytrends.related_queries()
        except Exception as exc:  # noqa: BLE001
            if "429" in str(exc):
                log.info("[%s] 429 on %s — backing off 60s and retrying once",
                         self.name, region)
                time.sleep(60)
                pytrends.build_payload(batch, cat=0, timeframe="today 3-m", geo=region)
                return pytrends.interest_over_time(), pytrends.related_queries()
            raise

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        from pytrends.request import TrendReq  # optional dependency

        # Highest-priority keywords only (seeds first — see pipeline ordering).
        # Trends is the most aggressively rate-limited source here: an uncapped
        # 500-keyword universe means 100 batches per region and Google 429s
        # essentially all of it, burning hours of workflow time for nothing.
        cap = int(self.cfg.get("google_trends", {}).get("max_keywords", 60))
        keywords = keywords[:cap]

        pytrends = TrendReq(hl=self.cfg.get("language", "en-US"), tz=0, timeout=(10, 30))
        regions = self._regions_for_today()
        lang = (self.cfg.get("languages") or ["en"])[0]
        log.info("[%s] regions today: %s", self.name, regions)
        obs: list[Observation] = []
        discs: list[Discovery] = []
        date = today()

        for region in regions:
            for i in range(0, len(keywords), BATCH):
                batch = keywords[i:i + BATCH]
                try:
                    frame, related = self._fetch_batch(pytrends, batch, region)
                    if not frame.empty:
                        frame = frame.drop(columns=["isPartial"], errors="ignore")
                        for kw in batch:
                            if kw not in frame.columns:
                                continue
                            for ts, value in frame[kw].items():
                                obs.append(Observation(
                                    date=ts.strftime("%Y-%m-%d"), keyword=kw,
                                    source=self.name, metric="interest",
                                    value=float(value), region=region, language=lang,
                                ))
                    for kw in batch:
                        rising = (related.get(kw) or {}).get("rising")
                        if rising is None or rising.empty:
                            continue
                        for _, row in rising.head(10).iterrows():
                            discs.append(Discovery(
                                date=date, keyword=str(row["query"]), source=self.name,
                                context=f"rising related query for '{kw}' in {region}",
                                score=float(row.get("value", 0)),
                            ))
                except Exception as exc:  # noqa: BLE001 - 429s are expected
                    log.warning("[%s] %s batch %s failed: %s", self.name, region, batch, exc)
                time.sleep(3.0)  # be polite with the rate limiter
        return obs, discs

