from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

from trendpulse.collectors.base import Collector, today
from trendpulse.entities import is_brand_mention
from trendpulse.keywords import normalize
from trendpulse.types import Citation, Discovery, EntityMention, Observation

log = logging.getLogger(__name__)

BASE = "https://api.tryprofound.com"


def _rows(payload) -> list:
    """Rows from a Profound response, whichever shape it arrives in.

    The API answers with either a bare JSON list or an {info, data} envelope
    depending on endpoint and account. The old code called .get() straight on
    the payload, so a bare list crashed the whole collector with
    "'list' object has no attribute 'get'" — which safe_fetch then swallowed,
    silently zeroing every AI share-of-voice number for the day."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        return data if isinstance(data, list) else []
    return []


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
        categories = [c for c in _rows(self._get("/v1/org/categories"))
                      if isinstance(c, dict)]
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

    # v1 report facts, verified live against the ADCB category (2026-08-05, in
    # a sibling project) — do not "simplify" these away:
    #  * The per-asset leaderboard comes from POST /v1/reports/visibility with
    #    dimensions ["date", "asset_name"]. v2's group_by REJECTS any asset
    #    grouping ("asset" is not a legal value -> HTTP 422, seen in prod).
    #  * dimensions and metrics arrays in each response row come back in
    #    ALPHABETICAL field-name order, NOT request order. Positional reads
    #    silently transpose share_of_voice into visibility_score — always map
    #    with dict(zip(sorted(names), row[...])).
    #  * start_date must be STRICTLY before end_date (same-day windows 422).
    #  * Report data lags ~1 day; rows carry their own date dimension.
    VIS_METRICS = ("share_of_voice", "visibility_score")

    def _visibility(self, category: str, start: str, end: str
                    ) -> tuple[list[Observation], list[EntityMention]]:
        dims = ("asset_name", "date")
        rows = _rows(self._post("/v1/reports/visibility", {
            "category_id": category,
            "start_date": start,
            "end_date": end,
            "date_interval": "day",
            "metrics": list(self.VIS_METRICS),
            "dimensions": list(dims),
            "pagination": {"limit": 2000, "offset": 0},
        }))
        obs: list[Observation] = []
        mentions: list[EntityMention] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            named_dims = dict(zip(sorted(dims), row.get("dimensions") or []))
            named_mets = dict(zip(sorted(self.VIS_METRICS), row.get("metrics") or []))
            name = str(named_dims.get("asset_name") or "")
            date = str(named_dims.get("date") or "")[:10] or today()
            if not name:
                continue
            sov = named_mets.get("share_of_voice")
            vis = named_mets.get("visibility_score")
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

    MAX_ANSWER_PAGES = 5  # 5 x 200 = up to 1000 answers per run

    def _answers(self, category: str, start: str, end: str
                 ) -> tuple[list[Discovery], list[EntityMention]]:
        # /v2/prompts/answers paginates with {limit, cursor}; the default limit
        # is 10, which silently discards almost the whole day. model/topic
        # arrive as {id, name} objects.
        rows: list = []
        cursor: str | None = None
        for _page in range(self.MAX_ANSWER_PAGES):
            body: dict = {"category_id": category, "start_date": start,
                          "end_date": end, "limit": 200}
            if cursor:
                body["cursor"] = cursor
            payload = self._post("/v2/prompts/answers", body)
            rows.extend(_rows(payload))
            info = payload.get("info") if isinstance(payload, dict) else None
            cursor = (info or {}).get("next_cursor")
            if not cursor:
                break

        date = today()
        discs: list[Discovery] = []
        mentions: list[EntityMention] = []

        def _name(value, default: str) -> str:
            if isinstance(value, dict):
                return str(value.get("name") or default)
            return str(value or default)

        for row in rows:
            if not isinstance(row, dict):
                continue
            prompt = (row.get("prompt") or "").strip()
            model = _name(row.get("model"), "AI")
            norm = normalize(prompt)
            # prompts are longer than keywords — allow full questions up to 20 words
            if norm and 3 <= len(norm) <= 140 and norm.count(" ") <= 20:
                topic = _name(row.get("topic"), "—")
                discs.append(Discovery(
                    date=date, keyword=norm, source=self.name,
                    context=f"AI prompt ({model}) · topic: {topic}",
                    score=80.0,  # real questions AI engines answer — top AEO/GEO material
                ))
            for brand in row.get("mentions") or []:
                kind = "brand" if is_brand_mention(str(brand), self.asset) else "competitor"
                mentions.append(EntityMention(
                    date=date, entity=str(brand), kind=kind,
                    source=f"profound:{model}",
                    context=f"prompt: {prompt[:120]}", value=1.0))
            for url in row.get("citations") or []:
                url = str(url).strip()
                if not url.startswith("http"):
                    continue
                domain = urlparse(url).netloc.lower().removeprefix("www.")
                self.citations.append(Citation(
                    date=date, url=url, domain=domain, prompt=prompt, model=model,
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
