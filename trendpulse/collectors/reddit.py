from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from trendpulse.collectors.base import Collector, http_get, today
from trendpulse.keywords import is_question, normalize, valid_candidate
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)

API = "https://arctic-shift.photon-reddit.com/api/posts/search"

# Tokens ignored when matching keywords against post text: geo qualifiers
# (the subreddit already scopes geography) and generic stopwords.
SKIP_TOKENS = {
    "uae", "emirates", "dubai", "abu", "dhabi", "saudi", "arabia", "gcc",
    "mena", "qatar", "kuwait", "bahrain", "oman", "jordan", "lebanon",
    "the", "a", "an", "in", "on", "of", "for", "to", "and", "or", "is",
    "how", "what", "which", "best", "my", "i",
}


def _core_tokens(keyword: str) -> set[str]:
    return {t for t in keyword.lower().split() if t not in SKIP_TOKENS and len(t) > 1}


def _matches(tokens: set[str], text: str) -> bool:
    return bool(tokens) and all(t in text for t in tokens)


class RedditCollector(Collector):
    """Reddit via the Arctic Shift archive API (public, no Reddit API access
    required): https://arctic-shift.photon-reddit.com

    Design around its rate limits: ONE bulk fetch of the last 7 days of posts
    per subreddit (not per-keyword searches), then local keyword matching for
    mention counts and title harvesting for discoveries. Requests are paced
    and retried once on the API's soft 'slow down' response."""

    name = "reddit"

    def _recent_posts(self, sub: str, after: str) -> list[dict]:
        for attempt in (1, 2):
            resp = http_get(API, params={
                "subreddit": sub, "after": after, "limit": 100,
            }, timeout=45, retries=1)
            payload = resp.json()
            posts = payload.get("data")
            if posts is not None:
                return posts
            # {"data": null, "error": "Timeout. Maybe slow down a bit"}
            log.info("[%s] r/%s: %s (attempt %d)", self.name, sub,
                     payload.get("error", "empty response"), attempt)
            time.sleep(15 * attempt)
        return []

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        after = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        subreddits = self.cfg.get("reddit", {}).get("subreddits", ["dubai"])
        obs: list[Observation] = []
        discs: list[Discovery] = []
        counts: dict[str, float] = {kw: 0.0 for kw in keywords}
        token_map = {kw: _core_tokens(kw) for kw in keywords}

        # Titles only become discoveries when the post matches a tracked
        # keyword or names a tracked entity — a bulk subreddit feed is mostly
        # off-topic chatter otherwise. Entity matching uses word boundaries
        # ("Liv" must not match "delivery").
        import re as _re
        entities = self.cfg.get("entities", {})
        entity_rxs = [
            _re.compile(rf"(?<![a-z0-9]){_re.escape(e.lower())}(?![a-z0-9])")
            for e in (entities.get("brand", []) + entities.get("competitors", []))
        ]

        for sub in subreddits:
            try:
                posts = self._recent_posts(sub, after)
            except Exception as exc:  # noqa: BLE001
                log.debug("[%s] r/%s failed: %s", self.name, sub, exc)
                posts = []
            log.debug("[%s] r/%s: %d posts since %s", self.name, sub, len(posts), after)

            for post in posts:
                title = post.get("title") or ""
                text = f"{title} {post.get('selftext') or ''}".lower()
                matched = False
                for kw, tokens in token_map.items():
                    if _matches(tokens, text):
                        counts[kw] += 1.0
                        matched = True
                if not matched and not any(rx.search(text) for rx in entity_rxs):
                    continue
                norm = normalize(title)
                if valid_candidate(norm):
                    score = float(post.get("score") or 0)
                    discs.append(Discovery(
                        date=date, keyword=norm, source=self.name,
                        context=f"r/{sub}: https://reddit.com{post.get('permalink', '')}",
                        score=score + (10 if is_question(norm) else 0),
                    ))
            time.sleep(5)  # Arctic Shift asks for gentle pacing

        for kw, count in counts.items():
            obs.append(Observation(date=date, keyword=kw, source=self.name,
                                   metric="posts_7d", value=count))
        return obs, discs
