from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import calendar

from trendpulse.importers.base import (find_files, iso_date, iter_tables,
                                       map_columns, num)
from trendpulse.keywords import normalize, valid_candidate
from trendpulse.storage import Store
from trendpulse.types import Observation

log = logging.getLogger(__name__)

# GSC exports use "Top queries" (EN UI) but tolerate other spellings.
QUERY_COLS = ("query", "top queries", "top query", "search query", "keyword")
DATE_COLS = ("date", "day")
IMPRESSIONS_COLS = ("impressions", "impr")
CLICKS_COLS = ("clicks",)

# GSC aggregate exports (Queries.csv) carry no date — attribute rows to the
# export window encoded in the filename when present, otherwise to yesterday.
# Two filename conventions are recognized:
#   …_2026-07-01_2026-07-28.csv   -> the window's end date
#   GSC-Search-Performance-Jul-26.zip -> the month's last day
FILE_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
MONTH_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-_ ]*'?(\d{2}|\d{4})\b",
    re.IGNORECASE)
RECENCY_DAYS = 28

# Exports of GSC's Generative-AI search appearance report (queries where the
# site surfaced in AI Overviews / AI Mode) are stored under their own source:
# they are a *subset* of total search performance, and the observations table
# keys on (date, keyword, source, metric) — same-source imports of the same
# month would silently overwrite each other. Kept separate, they double as
# first-party GEO ground truth from Google itself.
AI_EXPORT_RE = re.compile(r"generative|ai[-_ ]?(overview|mode)", re.IGNORECASE)


def _file_date(name: str, index: int, total: int) -> str:
    matches = FILE_DATE_RE.findall(name)
    if matches:
        return matches[-1]
    month = MONTH_RE.search(name)
    if month:
        mon = MONTHS[month.group(1).lower()[:3]]
        year = int(month.group(2))
        year += 2000 if year < 100 else 0
        return f"{year:04d}-{mon:02d}-{calendar.monthrange(year, mon)[1]:02d}"
    day = datetime.now(timezone.utc) - timedelta(days=1 + min(index, RECENCY_DAYS))
    return day.strftime("%Y-%m-%d")


def import_gsc(store: Store, cfg: dict) -> int:
    """Import GSC dumps (Performance → Search results export — zip exactly as
    downloaded, or loose CSV/Excel, with or without a date column) as
    ground-truth demand: impressions = demand you were visible for, clicks =
    demand you captured. Generative-AI exports land as source `gsc_ai`."""
    directory = Path(cfg.get("imports", {}).get("gsc_dir", "data_imports/gsc"))
    files = find_files(directory, ["*.csv", "*.tsv", "*.xlsx", "*.xls", "*.zip"])
    if not files:
        log.info("[gsc] no files in %s — skipping", directory)
        return 0

    obs: list[Observation] = []
    for path in files:
        source = "gsc_ai" if AI_EXPORT_RE.search(path.name) else "gsc"
        for name, rows, headers in iter_tables(path):
            mapping = map_columns(headers, {
                "query": QUERY_COLS, "date": DATE_COLS,
                "impressions": IMPRESSIONS_COLS, "clicks": CLICKS_COLS,
            })
            if "query" not in mapping:
                log.debug("[gsc] %s has no query column — skipped", name)
                continue
            for idx, row in enumerate(rows):
                kw = normalize(str(row.get(mapping["query"], "")))
                if not valid_candidate(kw):
                    continue
                date = (iso_date(row.get(mapping["date"], ""))
                        if "date" in mapping else _file_date(name, idx, len(rows)))
                base = dict(keyword=kw, source=source, region="", language="")
                if "impressions" in mapping:
                    obs.append(Observation(date=date, metric="impressions",
                                           value=num(row[mapping["impressions"]]), **base))
                if "clicks" in mapping:
                    obs.append(Observation(date=date, metric="clicks",
                                           value=num(row[mapping["clicks"]]), **base))
    written = store.upsert_observations(obs)
    log.info("[gsc] imported %d observations from %d files", written, len(files))
    return written
