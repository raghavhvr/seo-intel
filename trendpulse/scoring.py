from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-6


def zscore(series: pd.Series, window: int = 28) -> pd.Series:
    """Rolling z-score of each point vs. the trailing `window` days."""
    baseline = series.shift(1).rolling(window, min_periods=7)
    mu, sd = baseline.mean(), baseline.std(ddof=0)
    return ((series - mu) / (sd + EPS)).clip(-8, 8).fillna(0.0)


def velocity_z(series: pd.Series) -> float:
    """How hot the last 7 days are vs. the prior 28 — the core trend signal."""
    if len(series) < 10:
        return 0.0
    recent = float(series.iloc[-7:].mean())
    prior = series.iloc[-35:-7]
    mu, sd = float(prior.mean()), float(prior.std(ddof=0))
    return float(np.clip((recent - mu) / (sd + EPS), -8, 8))


def momentum(series: pd.Series, short: int = 3, long: int = 14) -> float:
    """Difference of short and long trailing means — direction of travel."""
    if len(series) < long:
        return 0.0
    return float(series.iloc[-short:].mean() - series.iloc[-long:].mean())


def is_breakout(series: pd.Series, threshold: float = 2.0) -> bool:
    """True when the latest point sits `threshold` std-devs above baseline."""
    if len(series) < 10:
        return False
    prior = series.iloc[:-1].tail(28)
    sd = float(prior.std(ddof=0))
    return bool(series.iloc[-1] > float(prior.mean()) + threshold * (sd + EPS))


def stat_projected_delta(series: pd.Series, horizon_days: int) -> float:
    """Heuristic growth projection used until the ML model has enough history:
    current 7d velocity carried forward with horizon-dependent decay."""
    if len(series) < 14:
        return 0.0
    vel = float(series.iloc[-7:].mean() - series.iloc[-14:-7].mean())
    decay = {7: 1.0, 30: 0.6, 90: 0.3}.get(horizon_days, 0.5)
    return float(np.clip(vel * decay * (horizon_days / 7.0), -5, 5))
