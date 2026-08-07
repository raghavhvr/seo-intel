from __future__ import annotations

import logging
from pathlib import Path

from trendpulse.collectors import enabled_collectors
from trendpulse.config import db_path
from trendpulse.keywords import (is_relevant, keyword_universe, normalize,
                                 universe_tokens, valid_candidate)
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
        result = collector.safe_fetch(keywords)
        obs, discs = result[0], result[1]
        if len(result) > 2:  # Profound also returns entity mentions
            store.upsert_entity_mentions(result[2])
        total_obs += store.upsert_observations(obs)
        total_disc += store.upsert_discoveries(discs)
        new_discoveries.extend(discs)

    # Community share-of-voice: brand/competitor sightings in today's threads,
    # headlines and stories.
    from trendpulse.entities import scan_discoveries
    scan_discoveries(cfg, store, new_discoveries)

    # Fold the best new discoveries into the tracked universe by recording a
    # small observation for them — they become first-class keywords tomorrow.
    from datetime import date as _date

    from trendpulse.collectors.base import today
    from trendpulse.seasonality import prep_keywords

    cap = int(cfg["keywords"]["max_new_per_day"])
    known = set(universe) | set(store.observed_keywords())
    tokens = universe_tokens(known)
    added = 0
    for disc in sorted(new_discoveries, key=lambda d: d.score, reverse=True):
        if added >= cap:
            break
        kw = normalize(disc.keyword)
        if not valid_candidate(kw) or kw in known:
            continue
        if not is_relevant(kw, tokens, cfg):
            continue
        known.add(kw)
        store.upsert_observations([
            Observation(date=today(), keyword=kw, source="discovery",
                        metric="seed", value=float(disc.score))
        ])
        added += 1

    # Seasonal prep: inject keyword angles for regional moments that are
    # active now or inside their prep window (e.g. Ramadan offers content
    # needs to rank *before* the month starts).
    seasonal = 0
    for kw, event_name in prep_keywords(cfg, _date.today()):
        norm = normalize(kw)
        if not valid_candidate(norm):
            continue
        store.upsert_discoveries([Discovery(
            date=today(), keyword=norm, source="seasonal",
            context=f"upcoming regional moment: {event_name}", score=50.0,
        )])
        if norm not in known and added < cap:
            known.add(norm)
            store.upsert_observations([
                Observation(date=today(), keyword=norm, source="seasonal",
                            metric="seed", value=50.0)
            ])
            added += 1
            seasonal += 1
    log.info("ingest complete: %d observations, %d discoveries, %d new keywords"
             " (%d seasonal)", total_obs, total_disc, added, seasonal)
    store.close()
    return total_obs, total_disc


def run_import(cfg: dict) -> dict[str, int]:
    """Import offline data dumps (GSC / GA4 exports) from data_imports/."""
    from trendpulse.importers import import_ga4, import_gsc

    store = Store(db_path(cfg))
    results = {"gsc": import_gsc(store, cfg), "ga4": import_ga4(store, cfg)}
    store.close()
    return results


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
    """The full daily loop: offline dumps + fresh data -> retrain -> reports."""
    run_import(cfg)
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
