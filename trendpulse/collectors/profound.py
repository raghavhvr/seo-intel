from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone

import requests

from trendpulse.collectors.base import Collector, today
from trendpulse.entities import is_brand_mention
from trendpulse.keywords import normalize
from trendpulse.types import Discovery, EntityMention, Observation

log = logging.getLogger(__name__)

BASE = "https://api.tryprofound.com"


class ProfoundCollector(Collector):
    """TryProfound API — the GEO ground truth: how often AI engines mention
    and cite adcb.com for banking & finance prompts.

    Set PROFOUND_API_KEY (Enterprise plan, X-API-Key header). Optional:
    PROFOUND_CATEGORY_ID / PROFOUND_ASSET to skip auto-discovery. All POST
    report endpoints return an {info, data} envelope; V2 filter clauses are
    name-or-UUID based."""

    name = "profound"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.api_key = os.environ.get("PROFOUND_API_KEY", "")
        pcfg = cfg.get("profound", {})
        self.category_id = os.environ.get("PROFOUND_CATEGORY_ID") or pcfg.get("category_id")
        self.category_name = pcfg.get("category_name", "banking and finance")
        self.asset = os.environ.get("PROFOUND_ASSET") or pcfg.get("asset", "adcb.com")

    def available(self) -> bool:
        return bool(self.api_key)

    def _post(self, path: str, body: dict) -> dict:
        resp = requests.post(
            f"{BASE}{path}", json=body, timeout=60,
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str) -> dict:
        resp = requests.get(f"{BASE}{path}", timeout=30,
                            headers={"X-API-Key": self.api_key})
        resp.raise_for_status()
        return resp.json()

    def _resolve_category(self) -> str | None:
        if self.category_id:
            return self.category_id
        data = self._get("/v1/org/categories")
        categories = data.get("data", data if isinstance(data, list) else [])
        wanted = {t for t in re.split(r"[^a-z0-9]+", self.category_name.lower()) if t}
        best: tuple[int, dict | None] = (0, None)
        for cat in categories:
            name = str(cat.get("name", ""))
            tokens = {t for t in re.split(r"[^a-z0-9]+", name.lower()) if t}
            overlap = len(wanted & tokens)
            if overlap > best[0]:
                best = (overlap, cat)
        if best[0] > 0 and best[1] is not None:
            cat = best[1]
            return cat.get("id") or cat.get("uuid") or cat.get("name")
        if categories:
            log.warning("[%s] category '%s' not found; available: %s", self.name,
                        self.category_name,
                        [c.get("name") for c in categories][:10])
        return None

    def _visibility(self, category: str, start: str, end: str
                    ) -> tuple[list[Observation], list[EntityMention]]:
        body = {
            "category_id": category,
            "start_date": start,
            "end_date": end,
            "group_by": ["asset"],
            "metrics": ["visibility_score", "share_of_voice"],
        }
        rows = self._post("/v2/reports/visibility", body).get("data", [])
        date = today()
        obs: list[Observation] = []
        mentions: list[EntityMention] = []
        for row in rows:
            asset = row.get("asset") or {}
            name = asset.get("name") if isinstance(asset, dict) else str(asset or "")
            if not name:
                continue
            sov = row.get("share_of_voice")
            vis = row.get("visibility_score")
            if sov is not None:
                obs.append(Observation(date=date, keyword=normalize(name),
                                       source=self.name, metric="ai_share_of_voice",
                                       value=float(sov)))
            if vis is not None:
                obs.append(Observation(date=date, keyword=normalize(name),
                                       source=self.name, metric="ai_visibility",
                                       value=float(vis)))
            kind = "brand" if is_brand_mention(name, self.asset) else "competitor"
            mentions.append(EntityMention(
                date=date, entity=name, kind=kind, source="profound",
                context="AI share of voice (banking & finance)",
                metric="share_of_voice", value=float(sov or 0)))
        return obs, mentions

    def _answers(self, category: str, start: str, end: str
                 ) -> tuple[list[Discovery], list[EntityMention]]:
        rows = self._post("/v2/prompts/answers", {
            "category_id": category, "start_date": start, "end_date": end,
        }).get("data", [])
        date = today()
        discs: list[Discovery] = []
        mentions: list[EntityMention] = []
        for row in rows:
            prompt = (row.get("prompt") or "").strip()
            model = row.get("model") or "AI"
            norm = normalize(prompt)
            # prompts are longer than keywords — allow full questions up to 20 words
            if norm and 3 <= len(norm) <= 140 and norm.count(" ") <= 20:
                discs.append(Discovery(
                    date=date, keyword=norm, source=self.name,
                    context=f"AI prompt ({model}) · topic: {row.get('topic', '—')}",
                    score=80.0,  # real questions AI engines answer — top AEO/GEO material
                ))
            for brand in row.get("mentions") or []:
                kind = "brand" if is_brand_mention(str(brand), self.asset) else "competitor"
                mentions.append(EntityMention(
                    date=date, entity=str(brand), kind=kind,
                    source=f"profound:{model}",
                    context=f"prompt: {prompt[:120]}", value=1.0))
            for url in row.get("citations") or []:
                discs.append(Discovery(
                    date=date, keyword=f"[citation] {url}", source=self.name,
                    context=f"URL cited by {model} for: {prompt[:100]}",
                    score=60.0,
                ))
        return discs, mentions

    def fetch(self, keywords: list[str]
              ) -> tuple[list[Observation], list[Discovery], list[EntityMention]]:
        if not self.available():
            log.info("[%s] PROFOUND_API_KEY not set — skipping", self.name)
            return [], [], []
        end = datetime.now(timezone.utc) - timedelta(days=1)
        start = end - timedelta(days=7)
        category = self._resolve_category()
        if not category:
            return [], [], []
        obs, vis_mentions = self._visibility(category, str(start.date()), str(end.date()))
        discs, ans_mentions = self._answers(category, str(start.date()), str(end.date()))
        return obs, discs, vis_mentions + ans_mentions

    def safe_fetch(self, keywords: list[str]
                   ) -> tuple[list[Observation], list[Discovery], list[EntityMention]]:
        try:
            obs, discs, mentions = self.fetch(keywords)
            log.info("[%s] %d observations, %d discoveries, %d entity mentions",
                     self.name, len(obs), len(discs), len(mentions))
            return obs, discs, mentions
        except Exception as exc:  # noqa: BLE001 - never kill the pipeline
            log.warning("[%s] failed: %s", self.name, exc)
            return [], [], []
