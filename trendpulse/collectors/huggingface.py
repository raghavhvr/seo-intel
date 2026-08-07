from __future__ import annotations

import logging
import time

from trendpulse.collectors.base import Collector, http_get, today
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

API_URL = "https://huggingface.co/api/models"


class HuggingFaceCollector(Collector):
    """Hugging Face Hub API (official, open). Counts of matching models per
    keyword + the current trending-models list — a GEO signal showing which AI
    capabilities (and the jargon around them) are gaining traction."""

    name = "huggingface"

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        obs: list[Observation] = []
        discs: list[Discovery] = []

        for kw in keywords[:60]:
            try:
                resp = http_get(API_URL, params={
                    "search": kw, "sort": "lastModified", "direction": "-1",
                    "limit": 50,
                }, timeout=15, retries=1)
                obs.append(Observation(
                    date=date, keyword=kw, source=self.name,
                    metric="models", value=float(len(resp.json())),
                ))
            except Exception as exc:  # noqa: BLE001
                log.debug("[%s] search '%s' failed: %s", self.name, kw, exc)
            time.sleep(0.15)

        try:
            resp = http_get(API_URL, params={
                "sort": "likes", "direction": "-1", "limit": 50,
            }, timeout=15, retries=1)
            for model in resp.json():
                model_id = model.get("id", "")
                slug = model_id.split("/")[-1].replace("-", " ").replace("_", " ")
                if 3 <= len(slug) <= 80:
                    discs.append(Discovery(
                        date=date, keyword=slug, source=self.name,
                        context=f"trending model: https://huggingface.co/{model_id}",
                        score=float(model.get("likes", 0)),
                    ))
        except Exception as exc:  # noqa: BLE001
            log.debug("[%s] trending failed: %s", self.name, exc)
        return obs, discs
