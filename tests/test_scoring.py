import numpy as np
import pandas as pd

from trendpulse.scoring import (is_breakout, momentum, stat_projected_delta,
                                velocity_z, zscore)


def flat(n=60, value=10.0):
    return pd.Series([value] * n, dtype=float)


def test_velocity_z_flat_is_zero():
    assert abs(velocity_z(flat())) < 0.1


def test_velocity_z_detects_surge():
    series = flat(60)
    series.iloc[-7:] = 40.0
    assert velocity_z(series) > 2.0


def test_breakout():
    series = flat(60)
    assert not is_breakout(series)
    noisy = pd.Series(np.random.default_rng(1).normal(10, 1, 60))
    noisy.iloc[-1] = 30.0
    assert is_breakout(noisy)


def test_momentum_direction():
    rising = pd.Series(np.linspace(1, 30, 60))
    cooling = pd.Series(np.linspace(30, 1, 60))
    assert momentum(rising) > 0
    assert momentum(cooling) < 0


def test_zscore_bounds():
    series = pd.Series(np.random.default_rng(2).normal(0, 1, 100))
    z = zscore(series)
    assert z.abs().max() <= 8.0


def test_stat_projection_sign():
    rising = pd.Series(np.linspace(10, 30, 60))
    assert stat_projected_delta(rising, 7) > 0
    assert stat_projected_delta(rising[::-1].reset_index(drop=True), 30) < 0
