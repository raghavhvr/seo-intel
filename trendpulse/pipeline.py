from __future__ import annotations

import logging
from pathlib import Path

from trendpulse.collectors import enabled_collectors
from trendpulse.config import db_path
from trendpulse.keywords import keyword_universe, normalize, valid_candidate
from trendpulse.model import HorizonModel, load_models, train_all
from trendpulse.report import generate_report
from trendpulse.storage import Store
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)


def run_ingest(cfg: dict) -> tuple[int, int]:
    """One ingestion pass over all enabled collectors."""
    store = Store(db_path(cfg))
    universe = keyword_universe(cfg, store)
    keywords = sorted(universe)
    log.info("ingesting %d keywords from %d collectors",
             len(keywords), len(enabled_collectors(cfg)))

    total_obs = total_disc = 0
    new_discoveries: list[Discovery] = []
    for collector in enabled_collectors(cfg):
        obs, discs = collector.safe_fetch(keywords)
        total_obs += store.upsert_observations(obs)
        total_disc += store.upsert_discoveries(discs)
        new_discoveries.extend(discs)

    # Fold the best new discoveries into the tracked universe by recording a
    # small observation for them — they become first-class keywords tomorrow.
    from trendpulse.collectors.base import today
    cap = int(cfg["keywords"]["max_new_per_day"])
    known = set(universe) | set(store.observed_keywords())
    added = 0
    for disc in sorted(new_discoveries, key=lambda d: d.score, reverse=True):
        if added >= cap:
            break
        kw = normalize(disc.keyword)
        if not valid_candidate(kw) or kw in known:
            continue
        known.add(kw)
        store.upsert_observations([
            Observation(date=today(), keyword=kw, source="discovery",
                        metric="seed", value=float(disc.score))
        ])
        added += 1
    log.info("ingest complete: %d observations, %d discoveries, %d new keywords",
             total_obs, total_disc, added)
    store.close()
    return total_obs, total_disc


def run_train(cfg: dict) -> dict[str, HorizonModel]:
    """Retrain every horizon model on all history collected to date."""
    store = Store(db_path(cfg))
    universe = keyword_universe(cfg, store)
    models = train_all(store, cfg, universe)
    store.close()
    return models


def run_report(cfg: dict, models: dict[str, HorizonModel] | None = None) -> Path:
    store = Store(db_path(cfg))
    universe = keyword_universe(cfg, store)
    if models is None:
        models = load_models(cfg)
    path = generate_report(store, cfg, universe, models)
    store.close()
    return path


def run_daily(cfg: dict) -> Path:
    """The full daily loop: pull fresh data -> retrain -> regenerate reports."""
    run_ingest(cfg)
    models = run_train(cfg)
    return run_report(cfg, models)


def run_demo(cfg: dict, days: int = 150) -> Path:
    """Offline end-to-end run on synthetic data (no network needed)."""
    from trendpulse import synth

    store = Store(db_path(cfg))
    synth.generate(store, cfg, days=days)
    store.close()
    models = run_train(cfg)
    return run_report(cfg, models)
