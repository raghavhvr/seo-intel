from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from trendpulse.types import Citation, Discovery, EntityMention, Observation

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    date     TEXT NOT NULL,
    keyword  TEXT NOT NULL,
    source   TEXT NOT NULL,
    metric   TEXT NOT NULL,
    region   TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    value    REAL NOT NULL,
    raw      TEXT,
    PRIMARY KEY (date, keyword, source, metric, region, language)
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
CREATE TABLE IF NOT EXISTS entities (
    date    TEXT NOT NULL,
    entity  TEXT NOT NULL,
    kind    TEXT NOT NULL,
    source  TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '',
    metric  TEXT NOT NULL DEFAULT 'mention',
    value   REAL NOT NULL DEFAULT 1,
    PRIMARY KEY (date, entity, source, context, metric)
);
CREATE TABLE IF NOT EXISTS citations (
    date    TEXT NOT NULL,
    url     TEXT NOT NULL,
    domain  TEXT NOT NULL,
    prompt  TEXT NOT NULL,
    model   TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (date, url, prompt, model)
);
CREATE INDEX IF NOT EXISTS idx_obs_kw ON observations (keyword, date);
CREATE INDEX IF NOT EXISTS idx_disc_kw ON discoveries (keyword, date);
CREATE INDEX IF NOT EXISTS idx_entities ON entities (entity, date);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _ensure_schema(self) -> None:
        """Rebuild if an older observations table lacks region/language.

        The DB is a cache that daily ingestion (plus Trends/Wikipedia
        backfill) repopulates, so rebuilding is safe and cheap."""
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='observations'")
        if not cur.fetchone():
            return
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(observations)")}
        if {"region", "language"} <= cols:
            return
        import logging
        logging.getLogger(__name__).warning(
            "old schema detected — rebuilding %s (data is re-ingestible)", self.path)
        self.conn.executescript(
            "DROP TABLE IF EXISTS observations; DROP TABLE IF EXISTS discoveries;"
            " DROP TABLE IF EXISTS scores; DROP TABLE IF EXISTS model_runs;")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- writes -------------------------------------------------------------
    def upsert_observations(self, obs: list[Observation]) -> int:
        rows = [
            (o.date, o.keyword, o.source, o.metric, o.region, o.language,
             float(o.value), json.dumps(o.raw) if o.raw else None)
            for o in obs
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO observations"
            " (date, keyword, source, metric, region, language, value, raw)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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

    def upsert_entity_mentions(self, mentions: list[EntityMention]) -> int:
        rows = [(m.date, m.entity, m.kind, m.source, m.context, m.metric,
                 float(m.value)) for m in mentions]
        self.conn.executemany(
            "INSERT OR REPLACE INTO entities"
            " (date, entity, kind, source, context, metric, value)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def entity_visibility(self, days: int = 7) -> list[tuple[str, str, float, float]]:
        """(entity, kind, mentions, share_of_voice) over the trailing window."""
        cur = self.conn.execute(
            "SELECT entity, kind, SUM(value) FROM entities"
            " WHERE metric = 'mention' AND date >= date('now', ?)"
            " GROUP BY entity, kind ORDER BY 3 DESC",
            (f"-{days} days",),
        )
        rows = cur.fetchall()
        total = sum(r[2] for r in rows) or 1.0
        return [(e, k, v, 100.0 * v / total) for e, k, v in rows]

    def entity_contexts(self, entity: str, days: int = 30,
                        limit: int = 5) -> list[tuple[str, str, str]]:
        cur = self.conn.execute(
            "SELECT date, source, context FROM entities"
            " WHERE entity = ? AND context != '' AND date >= date('now', ?)"
            " ORDER BY date DESC LIMIT ?",
            (entity, f"-{days} days", limit),
        )
        return cur.fetchall()

    # -- citations ----------------------------------------------------------
    def upsert_citations(self, citations: list[Citation]) -> int:
        rows = [(c.date, c.url, c.domain, c.prompt, c.model) for c in citations]
        self.conn.executemany(
            "INSERT OR REPLACE INTO citations (date, url, domain, prompt, model)"
            " VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def citation_rows(self, days: int = 30) -> list[tuple[str, str, str, str, str]]:
        cur = self.conn.execute(
            "SELECT date, url, domain, prompt, model FROM citations"
            " WHERE date >= date('now', ?)",
            (f"-{days} days",),
        )
        return cur.fetchall()

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

    def wikipedia_mappings(self) -> list[tuple[str, str, str]]:
        """Distinct (source, keyword, article) triples already stored for the
        Wikipedia collector, read back out of each row's `raw` payload."""
        cur = self.conn.execute(
            "SELECT DISTINCT source, keyword, raw FROM observations"
            " WHERE source LIKE 'wikipedia%' AND raw IS NOT NULL"
        )
        out: list[tuple[str, str, str]] = []
        for source, keyword, raw in cur.fetchall():
            try:
                article = json.loads(raw).get("article")
            except (TypeError, ValueError):
                continue
            if article:
                out.append((source, keyword, str(article)))
        return out

    def delete_observations(self, source: str, keyword: str) -> int:
        cur = self.conn.execute(
            "DELETE FROM observations WHERE source = ? AND keyword = ?",
            (source, keyword),
        )
        self.conn.commit()
        return cur.rowcount

    def series(self, keyword: str) -> dict[tuple[str, str, str, str], dict[str, float]]:
        """All metric series for one keyword:
        {(source, metric, region, language): {date: value}}."""
        cur = self.conn.execute(
            "SELECT source, metric, region, language, date, value FROM observations"
            " WHERE keyword = ? ORDER BY date",
            (keyword,),
        )
        out: dict[tuple[str, str, str, str], dict[str, float]] = {}
        for source, metric, region, language, date, value in cur.fetchall():
            out.setdefault((source, metric, region, language), {})[date] = value
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
