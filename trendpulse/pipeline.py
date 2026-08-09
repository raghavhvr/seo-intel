from __future__ import annotations

import logging
from pathlib import Path

from trendpulse.collectors import enabled_collectors
from trendpulse.config import db_path
from trendpulse.keywords import (excluded_keywords, is_relevant,
                                 keyword_universe, normalize,
                                 universe_tokens, valid_candidate)
from trendpulse.model import HorizonModel, load_models, train_all
from trendpulse.report import generate_report
from trendpulse.storage import Store
from trendpulse.types import Discovery, Observation

log = logging.getLogger(__name__)


def run_ingest(cfg: dict) -> tuple[int, int]:
    """One ingestion pass over all enabled collectors."""
    from trendpulse.wikimatch import prune_stale_observations

    store = Store(db_path(cfg))
    # Retroactive: drops history collected under a keyword->article mapping
    # that today's gate or config rejects, so a matcher fix takes effect now
    # rather than after the old backfill ages out.
    prune_stale_observations(cfg, store)
    universe = keyword_universe(cfg, store)
    # Priority order, NOT alphabetical: keyword_universe lists config seeds
    # first, then discoveries by score. Collectors cap their request volume
    # with keywords[:N], so once the universe outgrows those caps (day two —
    # one day of discoveries is ~1000 candidates against a 500 cap), sorting
    # alphabetically would spend the whole budget on whatever starts with
    # 'best …' and starve the seeds the client actually cares about.
    keywords = list(universe)
    log.info("ingesting %d keywords from %d collectors",
             len(keywords), len(enabled_collectors(cfg)))

    total_obs = total_disc = 0
    new_discoveries: list[Discovery] = []
    for collector in enabled_collectors(cfg):
        result = collector.safe_fetch(keywords)
        obs, discs = result[0], result[1]
        if len(result) > 2:  # Profound also returns entity mentions
            store.upsert_entity_mentions(result[2])
        if collector.citations:
            store.upsert_citations(collector.citations)
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
    # Vouching vocabulary comes from the CLEAN universe, not from every
    # keyword ever observed: historical strays still in the observations
    # table ('flux1 schnell') would otherwise keep vouching for their own
    # kind long after the universe gate evicted them.
    tokens = universe_tokens(universe)
    excluded = excluded_keywords(cfg)
    added = 0
    for disc in sorted(new_discoveries, key=lambda d: d.score, reverse=True):
        if added >= cap:
            break
        kw = normalize(disc.keyword)
        if not valid_candidate(kw) or kw in known or kw in excluded:
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
    from trendpulse.dashboard import generate_dashboard

    store = Store(db_path(cfg))
    universe = keyword_universe(cfg, store)
    if models is None:
        models = load_models(cfg)
    path = generate_report(store, cfg, universe, models)
    # Two companion surfaces: reports/dashboard.html is the single-file page
    # (email-able, works from disk); docs/data.json feeds the React app that
    # GitHub Pages serves from docs/ — the app itself is built by
    # .github/workflows/dashboard.yml and only its DATA changes daily.
    from trendpulse.export import export_data

    out_dir = Path(cfg["reports"]["output_dir"])
    generate_dashboard(store, cfg, out_dir)
    export_data(store, cfg, [Path("docs/data.json")])
    store.close()
    return path


def run_dashboard(cfg: dict) -> Path:
    """Re-render the HTML dashboard from data already in the DB — no ingest,
    no training. Lets design changes reach the published page in seconds
    instead of waiting for the next full daily run."""
    from trendpulse.dashboard import generate_dashboard

    from trendpulse.export import export_data

    store = Store(db_path(cfg))
    try:
        path = generate_dashboard(store, cfg, Path(cfg["reports"]["output_dir"]))
        export_data(store, cfg, [Path("docs/data.json")])
        return path
    finally:
        store.close()


def run_notify(cfg: dict, report_path: Path | str = "") -> bool:
    from trendpulse.notify import send_alerts

    store = Store(db_path(cfg))
    try:
        return send_alerts(cfg, store, str(report_path))
    finally:
        store.close()


def run_daily(cfg: dict) -> Path:
    """The full daily loop: dumps + fresh data -> retrain -> report -> alerts."""
    run_import(cfg)
    run_ingest(cfg)
    models = run_train(cfg)
    path = run_report(cfg, models)
    run_notify(cfg, path)
    return path


def run_demo(cfg: dict, days: int = 150) -> Path:
    """Offline end-to-end run on synthetic data (no network needed)."""
    from trendpulse import synth

    store = Store(db_path(cfg))
    synth.generate(store, cfg, days=days)
    store.close()
    models = run_train(cfg)
    return run_report(cfg, models)
