from __future__ import annotations

import numpy as np
import pandas as pd

from trendpulse.storage import Store
from trendpulse.types import Discovery, Observation

PATTERNS = {
    "steady": lambda t, n: 40 + 3 * np.sin(2 * np.pi * t / 7) + np.random.normal(0, 2, n),
    "rising": lambda t, n: 20 + 0.35 * t + 3 * np.sin(2 * np.pi * t / 7) + np.random.normal(0, 2, n),
    "breakout": lambda t, n: np.where(t > n - 12, 20 + 0.35 * (n - 12), 20) +
                             np.where(t > n - 12, 6 * (t - (n - 12)), 0) +
                             3 * np.sin(2 * np.pi * t / 7) + np.random.normal(0, 2, n),
    "seasonal": lambda t, n: 30 + 15 * np.sin(2 * np.pi * t / 30) + np.random.normal(0, 2, n),
    "cooling": lambda t, n: np.maximum(60 - 0.4 * t, 5) + np.random.normal(0, 2, n),
}


def generate(store: Store, cfg: dict, days: int = 150, seed: int = 7) -> None:
    """Deterministic synthetic history so the demo/tests exercise the full
    pipeline (training included) without any network access."""
    rng = np.random.default_rng(seed)

    seeds = cfg.get("seeds", {})
    keywords: list[tuple[str, str]] = []
    for channel, kws in seeds.items():
        for kw in kws:
            keywords.append((kw, channel))
    if not keywords:
        keywords = [(f"topic {i}", "seo") for i in range(12)]
    # pad to a reasonable universe with extra synthetic topics
    extra = [(f"emerging topic {i}", None) for i in range(max(0, 30 - len(keywords)))]
    keywords = [(k, c) for k, c in keywords] + [(k, c) for k, c in extra]

    # rotate pattern assignment per seed so each run exercises the full mix
    patterns = list(PATTERNS)
    offset = seed % len(patterns)
    pattern_cycle = patterns[offset:] + patterns[:offset]
    dates = pd.date_range(end=pd.Timestamp.now("UTC").normalize() - pd.Timedelta(days=1),
                          periods=days, freq="D")
    t = np.arange(days)
    obs: list[Observation] = []
    discs: list[Discovery] = []

    for idx, (kw, _channel) in enumerate(keywords):
        pattern = pattern_cycle[idx % len(pattern_cycle)]
        base = np.maximum(PATTERNS[pattern](t, days), 0.1)
        for source, scale, noise in (
            ("google_trends", 1.0, 1.5),
            ("wikipedia", 60.0, 30.0),
            ("google_news", 0.25, 0.6),
            ("hackernews", 0.15, 0.4),
            ("reddit", 0.3, 0.8),
            ("stackexchange", 0.1, 0.3),
        ):
            metric = {"google_trends": "interest", "wikipedia": "pageviews"}.get(source, "mentions")
            values = np.maximum(base * scale + rng.normal(0, noise, days), 0)
            for d, v in zip(dates, values):
                obs.append(Observation(date=str(d.date()), keyword=kw,
                                       source=source, metric=metric, value=float(v)))
        if pattern in ("rising", "breakout"):
            discs.append(Discovery(date=str(dates[-1].date()), keyword=kw,
                                   source="synthetic", context="synthetic rising query",
                                   score=float(100 - idx)))

    store.upsert_observations(obs)
    store.upsert_discoveries(discs)
