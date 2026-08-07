from __future__ import annotations

import logging

from trendpulse.collectors.arxiv import ArxivCollector
from trendpulse.collectors.autocomplete import AutocompleteCollector
from trendpulse.collectors.base import Collector
from trendpulse.collectors.google_news import GoogleNewsCollector
from trendpulse.collectors.google_trends import GoogleTrendsCollector
from trendpulse.collectors.hackernews import HackerNewsCollector
from trendpulse.collectors.huggingface import HuggingFaceCollector
from trendpulse.collectors.profound import ProfoundCollector
from trendpulse.collectors.reddit import RedditCollector
from trendpulse.collectors.stackexchange import StackExchangeCollector
from trendpulse.collectors.wikipedia import WikipediaCollector

log = logging.getLogger(__name__)

REGISTRY: dict[str, type[Collector]] = {
    "google_trends": GoogleTrendsCollector,
    "autocomplete": AutocompleteCollector,
    "wikipedia": WikipediaCollector,
    "hackernews": HackerNewsCollector,
    "reddit": RedditCollector,
    "stackexchange": StackExchangeCollector,
    "google_news": GoogleNewsCollector,
    "arxiv": ArxivCollector,
    "huggingface": HuggingFaceCollector,
    "profound": ProfoundCollector,
}


def enabled_collectors(cfg: dict) -> list[Collector]:
    collectors: list[Collector] = []
    for name, cls in REGISTRY.items():
        if not cfg.get("sources", {}).get(name, False):
            continue
        if name == "google_trends":
            try:
                import pytrends  # noqa: F401
            except ImportError:
                log.warning("google_trends enabled but pytrends not installed — skipping")
                continue
        if name == "profound" and not ProfoundCollector(cfg).available():
            continue  # silent unless PROFOUND_API_KEY is set
        collectors.append(cls(cfg))
    return collectors
