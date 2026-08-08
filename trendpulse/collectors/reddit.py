from __future__ import annotations

import logging
import os
import time

import feedparser
import requests

from trendpulse.collectors.base import USER_AGENT, Collector, http_get, today
from trendpulse.keywords import is_question, normalize, valid_candidate
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)


class RedditCollector(Collector):
    """Reddit mentions + rising threads in UAE/GCC and money subreddits.

    Access strategy, in order:
    1. Free OAuth (script app) when REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET
       are set — most reliable.
    2. Public JSON endpoints — frequently 403 from datacenter IPs.
    3. Public RSS feeds (search.rss / hot.rss) — no auth needed; scores are
       unavailable so discoveries get a flat score (+ question bonus).
    """

    name = "reddit"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self._token: str | None = None
        self._json_blocked = False

    def _oauth_token(self) -> str | None:
        if self._token:
            return self._token
        client_id = os.environ.get("REDDIT_CLIENT_ID")
        secret = os.environ.get("REDDIT_CLIENT_SECRET")
        if not client_id or not secret:
            return None
        resp = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(client_id, secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": USER_AGENT}, timeout=15,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _search(self, sub: str, kw: str) -> list[dict]:
        """Recent posts matching kw in a subreddit: [{title, url, score}]."""
        token = self._oauth_token()
        if token:
            data = http_get(f"https://oauth.reddit.com/r/{sub}/search", params={
                "q": kw, "restrict_sr": "1", "sort": "new", "t": "week", "limit": 25,
            }, headers={"Authorization": f"Bearer {token}"}, timeout=15, retries=1).json()
            return [{"title": c["data"].get("title", ""),
                     "url": f"https://reddit.com{c['data'].get('permalink', '')}",
                     "score": float(c["data"].get("score") or 0)}
                    for c in data.get("data", {}).get("children", [])]
        if not self._json_blocked:
            try:
                data = http_get(f"https://www.reddit.com/r/{sub}/search.json", params={
                    "q": kw, "restrict_sr": "1", "sort": "new", "t": "week", "limit": 25,
                }, timeout=15, retries=0).json()
                return [{"title": c["data"].get("title", ""),
                         "url": f"https://reddit.com{c['data'].get('permalink', '')}",
                         "score": float(c["data"].get("score") or 0)}
                        for c in data.get("data", {}).get("children", [])]
            except Exception as exc:  # noqa: BLE001 - usually a 403 wall
                log.info("[%s] JSON endpoint blocked (%s) — falling back to RSS",
                         self.name, exc)
                self._json_blocked = True
        feed = feedparser.parse(
            f"https://www.reddit.com/r/{sub}/search.rss?q={requests.utils.quote(kw)}"
            f"&restrict_sr=1&sort=new&t=week",
            request_headers={"User-Agent": USER_AGENT})
        return [{"title": e.get("title", ""), "url": e.get("link", ""), "score": 1.0}
                for e in feed.entries]

    def _hot(self, sub: str) -> list[dict]:
        token = self._oauth_token()
        if token or not self._json_blocked:
            try:
                if token:
                    data = http_get(f"https://oauth.reddit.com/r/{sub}/hot",
                                    params={"limit": 30},
                                    headers={"Authorization": f"Bearer {token}"},
                                    timeout=15, retries=1).json()
                else:
                    data = http_get(f"https://www.reddit.com/r/{sub}/hot.json",
                                    params={"limit": 30}, timeout=15, retries=0).json()
                return [{"title": c["data"].get("title", ""),
                         "url": f"https://reddit.com{c['data'].get('permalink', '')}",
                         "score": float(c["data"].get("score") or 0)}
                        for c in data.get("data", {}).get("children", [])]
            except Exception:  # noqa: BLE001
                self._json_blocked = True
        feed = feedparser.parse(f"https://www.reddit.com/r/{sub}/hot/.rss",
                                request_headers={"User-Agent": USER_AGENT})
        return [{"title": e.get("title", ""), "url": e.get("link", ""), "score": 1.0}
                for e in feed.entries]

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        subreddits = self.cfg.get("reddit", {}).get("subreddits", ["dubai"])
        obs: list[Observation] = []
        discs: list[Discovery] = []

        for kw in keywords[:80]:
            total = 0.0
            for sub in subreddits[:4]:
                try:
                    posts = self._search(sub, kw)
                    total += len(posts)
                    for post in posts[:3]:
                        title = normalize(post["title"])
                        if valid_candidate(title):
                            discs.append(Discovery(
                                date=date, keyword=title, source=self.name,
                                context=f"r/{sub}: {post['url']}",
                                score=post["score"] + (10 if is_question(title) else 0),
                            ))
                except Exception as exc:  # noqa: BLE001
                    log.debug("[%s] r/%s '%s' failed: %s", self.name, sub, kw, exc)
                time.sleep(0.4)
            obs.append(Observation(date=date, keyword=kw, source=self.name,
                                   metric="posts_7d", value=total))

        for sub in subreddits:
            try:
                for post in self._hot(sub):
                    title = normalize(post["title"])
                    if valid_candidate(title):
                        discs.append(Discovery(
                            date=date, keyword=title, source=self.name,
                            context=f"hot in r/{sub}: {post['url']}",
                            score=post["score"] + (10 if is_question(title) else 0),
                        ))
            except Exception as exc:  # noqa: BLE001
                log.debug("[%s] r/%s hot failed: %s", self.name, sub, exc)
            time.sleep(0.4)
        return obs, discs
