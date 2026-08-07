from __future__ import annotations

import logging
import time

from trendpulse.collectors.base import Collector, http_get, today
from trendpulse.keywords import is_question, normalize, valid_candidate
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

URL = "https://suggestqueries.google.com/complete/search"

# Modifier prefixes surface commercial and question-style variants of seeds.
MODIFIERS = ["", "how to ", "what is ", "why ", "best ", "vs ", "for ", "cost of "]


class AutocompleteCollector(Collector):
    """Google autocomplete suggestions — free JSON endpoint, updates in real
    time. Suggestions are keyword discoveries (question-shaped ones feed AEO)."""

    name = "autocomplete"

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        discs: list[Discovery] = []
        seen: set[str] = set()
        gl = (self.cfg.get("region") or "US").lower()
        hl = (self.cfg.get("language") or "en-US").split("-")[0]

        for kw in keywords[:60]:  # bound the request count per run
            for modifier in MODIFIERS:
                query = f"{modifier}{kw}"
                try:
                    resp = http_get(URL, params={
                        "client": "firefox", "q": query, "hl": hl, "gl": gl,
                    }, timeout=10, retries=1)
                    suggestions = resp.json()[1]
                except Exception as exc:  # noqa: BLE001
                    log.debug("[%s] '%s' failed: %s", self.name, query, exc)
                    continue
                for rank, suggestion in enumerate(suggestions):
                    norm = normalize(str(suggestion))
                    if not valid_candidate(norm) or norm in seen or norm == kw:
                        continue
                    seen.add(norm)
                    kind = "question suggestion" if is_question(norm) else "suggestion"
                    discs.append(Discovery(
                        date=date, keyword=norm, source=self.name,
                        context=f"{kind} for '{query}'",
                        score=float(len(suggestions) - rank),
                    ))
                time.sleep(0.15)
        return [], discs
