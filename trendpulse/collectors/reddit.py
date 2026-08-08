from __future__ import annotations

import logging
import os
import time

import requests

from trendpulse.collectors.base import USER_AGENT, Collector, http_get, today
from trendpulse.keywords import is_question, normalize, valid_candidate
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)


class RedditCollector(Collector):
    """Reddit mentions + rising threads in marketing/AI subreddits.

    Uses free OAuth (script app) when REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET
    are set; otherwise falls back to the public JSON endpoints, which Reddit
    sometimes rate-limits — failures are logged and skipped.
    """

    name = "reddit"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self._token: str | None = None

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

    def _get(self, url: str, params: dict) -> dict:
        token = self._oauth_token()
        if token:
            resp = http_get(f"https://oauth.reddit.com{url}", params=params,
                            headers={"Authorization": f"Bearer {token}"},
                            timeout=15, retries=1)
            return resp.json()
        resp = http_get(f"https://www.reddit.com{url}.json", params=params,
                        timeout=15, retries=1)
        return resp.json()

    def fetch(self, keywords: list[str]) -> tuple[list[Observation], list[Discovery]]:
        date = today()
        subreddits = self.cfg.get("reddit", {}).get("subreddits", ["marketing"])
        obs: list[Observation] = []
        discs: list[Discovery] = []

        for kw in keywords[:80]:
            total = 0.0
            for sub in subreddits[:4]:
                try:
                    data = self._get(f"/r/{sub}/search", {
                        "q": kw, "restrict_sr": "1", "sort": "new",
                        "t": "week", "limit": 25,
                    })
                    children = data.get("data", {}).get("children", [])
                    total += len(children)
                    for child in children[:3]:
                        post = child.get("data", {})
                        title = normalize(post.get("title") or "")
                        if valid_candidate(title):
                            discs.append(Discovery(
                                date=date, keyword=title, source=self.name,
                                context=f"r/{sub}: https://reddit.com{post.get('permalink', '')}",
                                score=float(post.get("score") or 0) + (10 if is_question(title) else 0),
                            ))
                except Exception as exc:  # noqa: BLE001
                    log.debug("[%s] r/%s '%s' failed: %s", self.name, sub, kw, exc)
                time.sleep(0.4)
            obs.append(Observation(date=date, keyword=kw, source=self.name,
                                   metric="posts_7d", value=total))

        for sub in subreddits:
            try:
                data = self._get(f"/r/{sub}/hot", {"limit": 30})
                for child in data.get("data", {}).get("children", []):
                    post = child.get("data", {})
                    title = normalize(post.get("title") or "")
                    if valid_candidate(title):
                        discs.append(Discovery(
                            date=date, keyword=title, source=self.name,
                            context=f"hot in r/{sub}",
                            score=float(post.get("score") or 0) + (10 if is_question(title) else 0),
                        ))
            except Exception as exc:  # noqa: BLE001
                log.debug("[%s] r/%s hot failed: %s", self.name, sub, exc)
            time.sleep(0.4)
        return obs, discs
