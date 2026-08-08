from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from trendpulse.collectors.base import Collector, http_get
from trendpulse.types import Discovery, Observation
from trendpulse.wikimatch import best_match, configured_article

log = logging.getLogger(__name__)

SEARCH_LIMIT = 5  # candidates to consider before giving up on a keyword


class WikipediaCollector(Collector):
    """Wikimedia Pageviews API (official, open data, daily updates), one
    Wikipedia edition per configured language (e.g. en + ar for the Gulf).
    Resolves each keyword to an article, then backfills ~60 days of daily
    pageviews.

    Resolution is gated (see `trendpulse.wikimatch`): the search API's top hit
    is accepted only when its title covers every content token of the keyword.
    Keywords with no encyclopaedic equivalent — most localized commercial
    queries, e.g. 'car loan uae' — contribute nothing rather than borrowing an
    unrelated article's traffic. Curate real mappings under `wikipedia.articles`
    in config.yaml; those bypass the gate.

    Pageviews are global per edition (the API has no country filter), so treat
    this as a topic-level interest signal, not localized demand.
    """

    name = "wikipedia"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.rejected: list[tuple[str, str, str]] = []  # (lang, keyword, top candidate)

    def _candidates(self, project: str, keyword: str) -> list[str]:
        resp = http_get(f"https://{project}/w/api.php", params={
            "action": "query", "list": "search", "srsearch": keyword,
            "format": "json", "srlimit": SEARCH_LIMIT,
        }, timeout=15, retries=1)
        results = resp.json().get("query", {}).get("search", [])
        return [r["title"] for r in results if r.get("title")]

    def _resolve_title(self, project: str, keyword: str, lang: str) -> str | None:
        """Curated override first, then the gated search match."""
        pinned = configured_article(self.cfg, keyword, lang)
        if pinned:
            return pinned
        candidates = self._candidates(project, keyword)
        title = best_match(keyword, candidates)
        if title is None and candidates:
            self.rejected.append((lang, keyword, candidates[0]))
        return title

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        obs: list[Observation] = []
        end = datetime.now(timezone.utc) - timedelta(days=1)
        start = end - timedelta(days=60)
        rng = f"{start:%Y%m%d}00/{end:%Y%m%d}00"
        languages = self.cfg.get("languages") or ["en"]
        matched = 0

        # keywords arrive seeds-first; cap the per-edition search volume so a
        # grown universe (500 keywords -> 1000 searches) can't stall the run.
        for lang in languages:
            project = f"{lang}.wikipedia.org"
            for kw in keywords[:150]:
                try:
                    title = self._resolve_title(project, kw, lang)
                    if not title:
                        continue
                    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/"
                           f"per-article/{project}/all-access/all-agents/"
                           f"{title.replace(' ', '_')}/daily/{rng}")
                    resp = http_get(url, timeout=15, retries=1)
                    items = resp.json().get("items", [])
                    if items:
                        matched += 1
                        log.debug("[%s] %s: '%s' -> %s", self.name, lang, kw, title)
                    for item in items:
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

        # Logged every run: this is the audit trail for curating
        # `wikipedia.articles` — a rejection whose top hit looks plausible is a
        # mapping worth adding by hand.
        examples = "; ".join(f"{kw!r} -> {top!r}" for _lang, kw, top in self.rejected[:3])
        log.info("[%s] %d keyword/edition pairs matched an article, %d rejected"
                 " as off-topic%s", self.name, matched, len(self.rejected),
                 f" (e.g. {examples})" if examples else "")
        return obs, []
