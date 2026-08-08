from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

from trendpulse.types import Citation, Discovery, Observation

log = logging.getLogger(__name__)

USER_AGENT = "trendpulse/0.1 (open-source SEO/AEO/GEO trend tool; contact: configure-in-config.yaml)"


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def http_get(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: int = 20, retries: int = 2, backoff: float = 2.0) -> requests.Response:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, headers=hdrs, timeout=timeout)
            if resp.status_code == 429 and attempt < retries:
                time.sleep(backoff * (attempt + 1) * 2)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    raise last_exc  # type: ignore[misc]


class Collector:
    """Base class. fetch() must never raise — log and return what you have."""

    name = "base"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.citations: list[Citation] = []  # populated by fetch() where applicable

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        raise NotImplementedError

    def safe_fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        try:
            obs, discs = self.fetch(keywords)
            log.info("[%s] %d observations, %d discoveries", self.name, len(obs), len(discs))
            return obs, discs
        except Exception as exc:  # noqa: BLE001 - collectors must not kill the pipeline
            log.warning("[%s] failed: %s", self.name, exc)
            return [], []
