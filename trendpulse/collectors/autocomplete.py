from __future__ import annotations

import logging
import time

from trendpulse.collectors.base import Collector, http_get, today
from trendpulse.keywords import is_question, normalize, valid_candidate
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

URL = "https://suggestqueries.google.com/complete/search"

# Modifier prefixes surface commercial and question-style variants of seeds.
MODIFIERS = {
    "en": ["", "how to ", "what is ", "why ", "best ", "vs ", "for ", "cost of "],
    "ar": ["", "كيف ", "ما هو ", "أفضل ", "هل "],
}


class AutocompleteCollector(Collector):
    """Google autocomplete suggestions per country × language — free JSON
    endpoint, updates in real time. Suggestions are keyword discoveries
    (question-shaped ones feed AEO). Arabic modifiers surface Gulf-market
    question phrasing."""

    name = "autocomplete"

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        discs: list[Discovery] = []
        seen: set[str] = set()
        regions = [r.lower() for r in (self.cfg.get("regions") or [self.cfg.get("region", "US")])]
        languages = self.cfg.get("languages") or ["en"]

        for kw in keywords[:60]:  # bound the request count per run
            for region in regions[:3]:
                for lang in languages:
                    for modifier in MODIFIERS.get(lang, MODIFIERS["en"]):
                        query = f"{modifier}{kw}"
                        try:
                            resp = http_get(URL, params={
                                "client": "firefox", "q": query, "hl": lang, "gl": region,
                            }, timeout=10, retries=1)
                            suggestions = resp.json()[1]
                        except Exception as exc:  # noqa: BLE001
                            log.debug("[%s] '%s' (%s/%s) failed: %s",
                                      self.name, query, region, lang, exc)
                            continue
                        for rank, suggestion in enumerate(suggestions):
                            norm = normalize(str(suggestion))
                            if not valid_candidate(norm) or norm in seen or norm == kw:
                                continue
                            seen.add(norm)
                            kind = "question suggestion" if is_question(norm) else "suggestion"
                            discs.append(Discovery(
                                date=date, keyword=norm, source=self.name,
                                context=f"{kind} for '{query}' [{region.upper()}/{lang}]",
                                score=float(len(suggestions) - rank),
                            ))
                        time.sleep(0.15)
        return [], discs
