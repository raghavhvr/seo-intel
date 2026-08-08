from __future__ import annotations

import logging

from trendpulse.collectors.base import Collector, http_get, today
from trendpulse.keywords import normalize
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

API = "https://eonet.gsfc.nasa.gov/api/v3/events"


def _in_bbox(coords: list, bbox: list[float]) -> bool:
    """bbox = [west, south, east, north]; coords = [lon, lat]."""
    west, south, east, north = bbox
    lon, lat = coords[0], coords[1]
    return west <= lon <= east and south <= lat <= north


def _event_points(event: dict) -> list[list]:
    return [g["coordinates"] for g in event.get("geometry", [])
            if g.get("type") == "Point" and g.get("coordinates")]


class EonetCollector(Collector):
    """NASA EONET (Earth Observatory Natural Event Tracker) — official, open,
    no auth. Natural events move banking demand: Gulf floods spike insurance
    claim / emergency finance searches, disasters in remittance-corridor
    countries (India, Pakistan, Philippines) spike money-transfer queries.

    Relevance is enforced in two ways:
    1. Geography — events are filtered CLIENT-SIDE against configured
       bounding boxes (EONET's server-side `bbox` leaks out-of-box events
       when combined with `status=all`).
    2. Curation — only event categories mapped to keyword angles in config
       produce signal; everything else is ignored.

    Quiet periods are normal (zero events in the Gulf for months at a time);
    the collector then simply contributes nothing.
    """

    name = "eonet"

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        eonet_cfg = self.cfg.get("eonet", {})
        regions: dict = eonet_cfg.get("regions", {})
        if not regions:
            return [], []
        window = int(eonet_cfg.get("window_days", 30))
        date = today()

        resp = http_get(API, params={"days": window, "status": "all"},
                        timeout=30, retries=2)
        events = resp.json().get("events", [])
        log.info("[%s] %d global events in last %dd", self.name, len(events), window)

        obs: list[Observation] = []
        discs: list[Discovery] = []
        for region_name, region in regions.items():
            bbox = region.get("bbox")
            mapping: dict = region.get("category_keywords", {})
            if not bbox or not mapping:
                continue

            # events in this region, grouped by mapped category
            hits: dict[str, list[dict]] = {}
            for event in events:
                if not any(_in_bbox(p, bbox) for p in _event_points(event)):
                    continue
                for cat in event.get("categories", []):
                    if cat.get("id") in mapping:
                        hits.setdefault(cat["id"], []).append(event)

            for cat_id, cat_events in hits.items():
                titles = "; ".join(e.get("title", "")[:60] for e in cat_events[:3])
                log.info("[%s] %s/%s: %d active event(s): %s",
                         self.name, region_name, cat_id, len(cat_events), titles)
                for angle in mapping[cat_id]:
                    kw = normalize(angle)
                    if not kw:
                        continue
                    obs.append(Observation(
                        date=date, keyword=kw, source=self.name,
                        metric="active_events", value=float(len(cat_events)),
                        region=region_name,
                    ))
                    discs.append(Discovery(
                        date=date, keyword=kw, source=self.name,
                        context=f"natural event ({region_name}/{cat_id}): {titles}",
                        score=60.0,
                    ))
        return obs, discs
