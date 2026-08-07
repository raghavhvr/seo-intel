from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from trendpulse.config import model_dir
from trendpulse.features import FEATURES, build_training_set
from trendpulse.storage import Store

log = logging.getLogger(__name__)


@dataclass
class HorizonModel:
    horizon: str
    horizon_days: int
    estimator: object
    n_samples: int
    mae: float | None

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.estimator.predict(frame[FEATURES].fillna(0.0))


def _model_path(cfg: dict, horizon: str) -> Path:
    return model_dir(cfg) / f"{horizon}.joblib"


def train_horizon(store: Store, cfg: dict, universe: dict[str, str | None],
                  horizon: str, horizon_days: int) -> HorizonModel | None:
    """Train one horizon model on all history collected so far.

    Evaluation is a time-based split (last 20% of sample dates as holdout) so
    the reported MAE reflects genuine forward-looking accuracy. Returns None
    until enough labelled history exists — the report then falls back to the
    statistical scorer."""
    X, y, dates = build_training_set(store, cfg, universe, horizon_days)
    min_samples = int(cfg["model"]["min_samples"])
    if len(X) < min_samples:
        log.info("[%s] only %d samples (< %d) — ML model not active yet",
                 horizon, len(X), min_samples)
        store.log_model_run(datetime.now(timezone.utc).isoformat(), horizon,
                            len(X), None, "insufficient history; statistical fallback")
        return None

    order = np.argsort(np.array(dates, dtype="datetime64[D]"))
    split = int(len(order) * 0.8)
    train_idx, test_idx = order[:split], order[split:]

    estimator = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.06, l2_regularization=1.0,
        early_stopping=True, random_state=42,
    )
    estimator.fit(X.iloc[train_idx], y.iloc[train_idx])
    mae = float(mean_absolute_error(y.iloc[test_idx], estimator.predict(X.iloc[test_idx]))) \
        if len(test_idx) else None

    # Final model refit on 100% of history — it ships to production.
    final = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.06, l2_regularization=1.0,
        early_stopping=False, random_state=42,
    )
    final.fit(X, y)

    model = HorizonModel(horizon=horizon, horizon_days=horizon_days,
                         estimator=final, n_samples=len(X), mae=mae)
    joblib.dump({"model": model, "features": FEATURES}, _model_path(cfg, horizon))
    store.log_model_run(datetime.now(timezone.utc).isoformat(), horizon,
                        len(X), mae, "ok")
    log.info("[%s] trained on %d samples, holdout MAE=%.4f", horizon, len(X),
             mae if mae is not None else float("nan"))
    return model


def train_all(store: Store, cfg: dict, universe: dict[str, str | None]
              ) -> dict[str, HorizonModel]:
    models: dict[str, HorizonModel] = {}
    for horizon, days in cfg["model"]["horizons"].items():
        model = train_horizon(store, cfg, universe, horizon, int(days))
        if model is not None:
            models[horizon] = model
    return models


def load_models(cfg: dict) -> dict[str, HorizonModel]:
    models: dict[str, HorizonModel] = {}
    for horizon in cfg["model"]["horizons"]:
        path = _model_path(cfg, horizon)
        if path.exists():
            try:
                models[horizon] = joblib.load(path)["model"]
            except Exception as exc:  # noqa: BLE001 - stale/corrupt artifact
                log.warning("could not load model %s: %s", path, exc)
    return models
