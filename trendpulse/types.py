from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Observation:
    """One numeric signal for a keyword on one day from one source."""

    date: str  # YYYY-MM-DD (UTC)
    keyword: str
    source: str  # e.g. "google_trends"
    metric: str  # e.g. "interest", "pageviews", "mentions"
    value: float
    raw: dict | None = field(default=None)


@dataclass
class Discovery:
    """A candidate keyword / question / topic found in the wild."""

    date: str
    keyword: str
    source: str
    context: str = ""  # headline, question title, URL, ...
    score: float = 0.0
