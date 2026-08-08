import pytest

from trendpulse import synth
from trendpulse.features import FEATURES, build_snapshot, build_training_set
from trendpulse.keywords import keyword_universe
from trendpulse.model import load_models, train_all
from trendpulse.report import generate_report, score_keywords
from trendpulse.storage import Store


@pytest.fixture()
def env(tmp_path):
    cfg = {
        "seeds": {"seo": ["crm software", "email marketing"],
                  "aeo": ["how to choose a crm"],
                  "geo": ["ai agents for marketing"]},
        "geo_terms": ["ai"],
        "entities": {"brand": [], "competitors": []},
        "model": {"min_samples": 100, "horizons": {"week": 7, "month": 30, "quarter": 90}},
        "keywords": {"max_universe": 100, "max_new_per_day": 10},
        "reports": {"top_n": 5, "output_dir": str(tmp_path / "reports")},
        "data_dir": str(tmp_path / "data"),
    }
    store = Store(tmp_path / "data" / "trendpulse.db")
    synth.generate(store, cfg, days=170)
    yield cfg, store
    store.close()


def test_training_set_shapes(env):
    cfg, store = env
    universe = keyword_universe(cfg, store)
    X, y, dates = build_training_set(store, cfg, universe, 7)
    assert list(X.columns) == FEATURES
    assert len(X) == len(y) == len(dates)
    assert len(X) > 100
    assert y.abs().max() <= 5.0


def test_snapshot_has_all_keywords(env):
    cfg, store = env
    universe = keyword_universe(cfg, store)
    snap = build_snapshot(store, cfg, universe)
    assert len(snap) >= len(universe) - 2
    assert set(FEATURES) <= set(snap.columns)


def test_model_trains_and_predicts(env):
    cfg, store = env
    cfg["data_dir"] = str(store.path.parent)
    universe = keyword_universe(cfg, store)
    models = train_all(store, cfg, universe)
    assert "week" in models  # 170 days is enough for the 7d horizon
    snap = build_snapshot(store, cfg, universe)
    preds = models["week"].predict(snap)
    assert len(preds) == len(snap)
    loaded = load_models(cfg)
    assert "week" in loaded


def test_report_generation(env, tmp_path):
    cfg, store = env
    cfg["data_dir"] = str(store.path.parent)
    universe = keyword_universe(cfg, store)
    models = train_all(store, cfg, universe)
    path = generate_report(store, cfg, universe, models)
    text = path.read_text()
    assert "# Trend report" in text
    assert "## This week" in text and "## This quarter" in text
    assert "### SEO" in text and "### AEO" in text and "### GEO" in text
    # a rising/breakout synthetic topic should surface near the top of SEO
    assert "crm software" in text
    assert (tmp_path / "reports" / "latest.md").exists()
    assert list((tmp_path / "reports").glob("*-week-seo.csv"))


def test_score_keywords_fallback_without_models(env):
    cfg, store = env
    universe = keyword_universe(cfg, store)
    scored = score_keywords(store, cfg, universe, models={})
    assert not scored.empty
    for horizon in ("week", "month", "quarter"):
        assert f"score_{horizon}" in scored.columns
