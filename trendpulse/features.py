from __future__ import annotations

import numpy as np
import pandas as pd

from trendpulse.keywords import channels_for, is_question
from trendpulse.storage import Store

FEATURES = [
    "att_lag1", "att_mean3", "att_mean7", "att_mean14", "att_mean28",
    "att_std28", "z7", "mom3", "mom7", "breadth7",
    "dow_sin", "dow_cos",
    "len_chars", "is_question", "ch_aeo", "ch_geo",
]

MIN_HISTORY = 35  # days of attention needed before a date can be a sample


def _calendar(dates: list[str]) -> pd.DatetimeIndex:
    return pd.to_datetime(pd.Series(sorted(set(dates)))).dt.normalize()


def blended_attention(series_map: dict[tuple[str, str], dict[str, float]],
                      index: pd.DatetimeIndex) -> tuple[pd.Series, pd.Series]:
    """Blend all source metrics into one daily 'attention' series per keyword.

    Each source series is z-scored over its own history first, so sources with
    wildly different scales (pageviews vs. 0-100 Trends interest) contribute
    comparably. Returns (attention, breadth) where breadth is the count of
    sources with above-baseline activity that day.
    """
    cols, breadth = [], pd.Series(0.0, index=index)
    for (_source, _metric), values in series_map.items():
        ser = pd.Series(values, dtype=float)
        ser.index = pd.to_datetime(ser.index)
        ser = ser.groupby(level=0).sum().reindex(index)
        if ser.notna().sum() < 5:
            continue
        mu, sd = float(ser.mean()), float(ser.std(ddof=0))
        z = ((ser - mu) / (sd if sd > 1e-9 else 1.0)).clip(-5, 5)
        cols.append(z.fillna(0.0))
        breadth = breadth + (z.fillna(-10) > 0).astype(float)
    if not cols:
        return pd.Series(0.0, index=index), breadth
    attention = pd.concat(cols, axis=1).mean(axis=1)
    return attention, breadth


def _row(attention: pd.Series, breadth: pd.Series, i: int) -> dict[str, float]:
    a = attention
    last = a.iloc[:i + 1]
    prior28 = a.iloc[max(0, i - 35):i - 6]
    mu28 = float(prior28.mean()) if len(prior28) else 0.0
    sd28 = float(prior28.std(ddof=0)) if len(prior28) > 1 else 0.0
    mean7 = float(a.iloc[max(0, i - 6):i + 1].mean())
    dow = a.index[i].dayofweek
    return {
        "att_lag1": float(a.iloc[i - 1]) if i >= 1 else 0.0,
        "att_mean3": float(a.iloc[max(0, i - 2):i + 1].mean()),
        "att_mean7": mean7,
        "att_mean14": float(a.iloc[max(0, i - 13):i + 1].mean()),
        "att_mean28": float(a.iloc[max(0, i - 27):i + 1].mean()),
        "att_std28": float(last.iloc[-28:].std(ddof=0)) if len(last) > 1 else 0.0,
        "z7": (mean7 - mu28) / (sd28 + 1e-6),
        "mom3": float(a.iloc[max(0, i - 2):i + 1].mean() - a.iloc[max(0, i - 9):i - 2].mean()),
        "mom7": mean7 - float(a.iloc[max(0, i - 20):i - 6].mean()),
        "breadth7": float(breadth.iloc[max(0, i - 6):i + 1].mean()),
        "dow_sin": float(np.sin(2 * np.pi * dow / 7)),
        "dow_cos": float(np.cos(2 * np.pi * dow / 7)),
    }


def _static_features(keyword: str, cfg: dict, seed_channel: str | None) -> dict[str, float]:
    channels = channels_for(keyword, cfg, seed_channel)
    return {
        "len_chars": float(len(keyword)),
        "is_question": float(is_question(keyword)),
        "ch_aeo": float("aeo" in channels),
        "ch_geo": float("geo" in channels),
    }


def keyword_attention(store: Store, universe: dict[str, str | None]
                      ) -> dict[str, tuple[pd.Series, pd.Series]]:
    """Blended attention + breadth for every keyword, on a shared calendar."""
    all_dates: list[str] = store.dates()
    if not all_dates:
        return {}
    index = _calendar(all_dates)
    out: dict[str, tuple[pd.Series, pd.Series]] = {}
    for kw in universe:
        series_map = store.series(kw)
        if not series_map:
            continue
        out[kw] = blended_attention(series_map, index)
    return out


def build_snapshot(store: Store, cfg: dict, universe: dict[str, str | None]
                   ) -> pd.DataFrame:
    """Feature rows for every keyword as of the latest available date."""
    attention = keyword_attention(store, universe)
    rows = []
    for kw, (att, breadth) in attention.items():
        if len(att) < 10:
            continue
        feats = _row(att, breadth, len(att) - 1)
        feats.update(_static_features(kw, cfg, universe.get(kw)))
        feats["keyword"] = kw
        feats["date"] = str(att.index[-1].date())
        feats["velocity_z"] = feats["z7"]
        rows.append(feats)
    return pd.DataFrame(rows)


def build_training_set(store: Store, cfg: dict, universe: dict[str, str | None],
                       horizon_days: int) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    """Self-supervised dataset: features at date t, label = change in mean
    attention between the week ending at t and the `horizon_days` after t.
    Labels come from data we already collected, so the model re-learns from
    every new day of ingestion with zero manual labelling."""
    attention = keyword_attention(store, universe)
    X_rows, y, sample_dates = [], [], []
    for kw, (att, breadth) in attention.items():
        n = len(att)
        static = _static_features(kw, cfg, universe.get(kw))
        for i in range(MIN_HISTORY, n - horizon_days):
            feats = _row(att, breadth, i)
            feats.update(static)
            current = float(att.iloc[i - 6:i + 1].mean())
            future = float(att.iloc[i + 1:i + 1 + horizon_days].mean())
            label = float(np.clip(future - current, -5, 5))
            X_rows.append(feats)
            y.append(label)
            sample_dates.append(str(att.index[i].date()))
    if not X_rows:
        return pd.DataFrame(columns=FEATURES), pd.Series(dtype=float), []
    return pd.DataFrame(X_rows)[FEATURES], pd.Series(y), sample_dates
