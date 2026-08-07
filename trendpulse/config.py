from __future__ import annotations

import copy
from pathlib import Path

import yaml

DEFAULTS: dict = {
    "project": "TrendPulse",
    "region": "US",
    "language": "en-US",
    "seeds": {"seo": [], "aeo": [], "geo": []},
    "entities": {"brand": [], "competitors": []},
    "geo_terms": [],
    "sources": {
        "google_trends": True,
        "autocomplete": True,
        "wikipedia": True,
        "hackernews": True,
        "reddit": True,
        "stackexchange": True,
        "google_news": True,
        "arxiv": True,
        "huggingface": True,
    },
    "reddit": {"subreddits": ["seo", "marketing"]},
    "stackexchange": {"sites": ["webmasters"]},
    "model": {"min_samples": 200, "horizons": {"week": 7, "month": 30, "quarter": 90}},
    "keywords": {"max_universe": 400, "max_new_per_day": 40},
    "reports": {"top_n": 20, "output_dir": "reports"},
    "data_dir": "data",
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | Path | None = None) -> dict:
    """Load config.yaml (or an explicit path), merged over defaults."""
    candidates = [Path(path)] if path else [Path("config.yaml"), Path("config.example.yaml")]
    for candidate in candidates:
        if candidate.exists():
            with candidate.open() as fh:
                user = yaml.safe_load(fh) or {}
            cfg = _merge(DEFAULTS, user)
            cfg["_config_path"] = str(candidate)
            return cfg
    cfg = _merge(DEFAULTS, {})
    cfg["_config_path"] = None
    return cfg


def db_path(cfg: dict) -> Path:
    data_dir = Path(cfg["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "trendpulse.db"


def model_dir(cfg: dict) -> Path:
    path = Path(cfg["data_dir"]) / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path
