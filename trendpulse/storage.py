from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from trendpulse.types import Discovery, Observation

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    date    TEXT NOT NULL,
    keyword TEXT NOT NULL,
    source  TEXT NOT NULL,
    metric  TEXT NOT NULL,
    value   REAL NOT NULL,
    raw     TEXT,
    PRIMARY KEY (date, keyword, source, metric)
);
CREATE TABLE IF NOT EXISTS discoveries (
    date    TEXT NOT NULL,
    keyword TEXT NOT NULL,
    source  TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    score   REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (date, keyword, source, context)
);
CREATE TABLE IF NOT EXISTS scores (
    date             TEXT NOT NULL,
    keyword          TEXT NOT NULL,
    horizon          TEXT NOT NULL,
    channel          TEXT NOT NULL,
    trend_score      REAL NOT NULL,
    predicted_delta  REAL NOT NULL,
    velocity_z       REAL NOT NULL,
    PRIMARY KEY (date, keyword, horizon, channel)
);
CREATE TABLE IF NOT EXISTS model_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    trained_at TEXT NOT NULL,
    horizon    TEXT NOT NULL,
    n_samples  INTEGER NOT NULL,
    mae        REAL,
    notes      TEXT
);
CREATE INDEX IF NOT EXISTS idx_obs_kw ON observations (keyword, date);
CREATE INDEX IF NOT EXISTS idx_disc_kw ON discoveries (keyword, date);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- writes -------------------------------------------------------------
    def upsert_observations(self, obs: list[Observation]) -> int:
        rows = [
            (o.date, o.keyword, o.source, o.metric, float(o.value),
             json.dumps(o.raw) if o.raw else None)
            for o in obs
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO observations (date, keyword, source, metric, value, raw)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def upsert_discoveries(self, discs: list[Discovery]) -> int:
        rows = [(d.date, d.keyword, d.source, d.context, float(d.score)) for d in discs]
        self.conn.executemany(
            "INSERT OR REPLACE INTO discoveries (date, keyword, source, context, score)"
            " VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def save_score(self, date: str, keyword: str, horizon: str, channel: str,
                   trend_score: float, predicted_delta: float, velocity_z: float) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO scores (date, keyword, horizon, channel,"
            " trend_score, predicted_delta, velocity_z) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (date, keyword, horizon, channel, trend_score, predicted_delta, velocity_z),
        )

    def log_model_run(self, trained_at: str, horizon: str, n_samples: int,
                      mae: float | None, notes: str = "") -> None:
        self.conn.execute(
            "INSERT INTO model_runs (trained_at, horizon, n_samples, mae, notes)"
            " VALUES (?, ?, ?, ?, ?)",
            (trained_at, horizon, n_samples, mae, notes),
        )
        self.conn.commit()

    # -- reads --------------------------------------------------------------
    def dates(self) -> list[str]:
        cur = self.conn.execute("SELECT DISTINCT date FROM observations ORDER BY date")
        return [r[0] for r in cur.fetchall()]

    def observed_keywords(self) -> list[str]:
        cur = self.conn.execute("SELECT DISTINCT keyword FROM observations ORDER BY keyword")
        return [r[0] for r in cur.fetchall()]

    def discovered_keywords(self, limit: int = 10000) -> list[tuple[str, float]]:
        cur = self.conn.execute(
            "SELECT keyword, MAX(score) AS s FROM discoveries"
            " GROUP BY keyword ORDER BY s DESC LIMIT ?",
            (limit,),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]

    def series(self, keyword: str) -> dict[tuple[str, str], dict[str, float]]:
        """All metric series for one keyword: {(source, metric): {date: value}}."""
        cur = self.conn.execute(
            "SELECT source, metric, date, value FROM observations WHERE keyword = ?"
            " ORDER BY date",
            (keyword,),
        )
        out: dict[tuple[str, str], dict[str, float]] = {}
        for source, metric, date, value in cur.fetchall():
            out.setdefault((source, metric), {})[date] = value
        return out

    def recent_discoveries(self, keyword: str, days: int = 30,
                           limit: int = 5) -> list[tuple[str, str, float]]:
        cur = self.conn.execute(
            "SELECT date, context, score FROM discoveries"
            " WHERE keyword = ? AND date >= date('now', ?)"
            " ORDER BY score DESC LIMIT ?",
            (keyword, f"-{days} days", limit),
        )
        return cur.fetchall()

    def latest_scores(self, date: str, horizon: str, channel: str,
                      limit: int = 50) -> list[tuple]:
        cur = self.conn.execute(
            "SELECT keyword, trend_score, predicted_delta, velocity_z FROM scores"
            " WHERE date = ? AND horizon = ? AND channel = ?"
            " ORDER BY trend_score DESC LIMIT ?",
            (date, horizon, channel, limit),
        )
        return cur.fetchall()

    def model_runs(self, limit: int = 10) -> list[tuple]:
        cur = self.conn.execute(
            "SELECT trained_at, horizon, n_samples, mae, notes FROM model_runs"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()
