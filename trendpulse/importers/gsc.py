from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from trendpulse.importers.base import find_files, map_columns, num, read_rows
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
# export window encoded in the filename when present (…_2026-07-01_2026-07-28),
# otherwise to yesterday.
FILE_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
RECENCY_DAYS = 28


def _file_date(path: Path, index: int, total: int) -> str:
    matches = FILE_DATE_RE.findall(path.name)
    if matches:
        return matches[-1]
    day = datetime.now(timezone.utc) - timedelta(days=1 + min(index, RECENCY_DAYS))
    return day.strftime("%Y-%m-%d")


def import_gsc(store: Store, cfg: dict) -> int:
    """Import GSC dumps (Performance → Search results → Queries/Pages export,
    CSV or Excel, with or without a date column) as ground-truth demand:
    impressions = demand you were visible for, clicks = demand you captured."""
    directory = Path(cfg.get("imports", {}).get("gsc_dir", "data_imports/gsc"))
    files = find_files(directory, ["*.csv", "*.tsv", "*.xlsx", "*.xls"])
    if not files:
        log.info("[gsc] no files in %s — skipping", directory)
        return 0

    obs: list[Observation] = []
    for path in files:
        rows, headers = read_rows(path)
        mapping = map_columns(headers, {
            "query": QUERY_COLS, "date": DATE_COLS,
            "impressions": IMPRESSIONS_COLS, "clicks": CLICKS_COLS,
        })
        if "query" not in mapping:
            log.debug("[gsc] %s has no query column — skipped", path.name)
            continue
        for idx, row in enumerate(rows):
            kw = normalize(str(row.get(mapping["query"], "")))
            if not valid_candidate(kw):
                continue
            date = (str(row.get(mapping["date"], "")).strip()[:10]
                    if "date" in mapping else _file_date(path, idx, len(rows)))
            base = dict(keyword=kw, source="gsc", region="", language="")
            if "impressions" in mapping:
                obs.append(Observation(date=date, metric="impressions",
                                       value=num(row[mapping["impressions"]]), **base))
            if "clicks" in mapping:
                obs.append(Observation(date=date, metric="clicks",
                                       value=num(row[mapping["clicks"]]), **base))
    written = store.upsert_observations(obs)
    log.info("[gsc] imported %d observations from %d files", written, len(files))
    return written
