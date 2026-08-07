from __future__ import annotations

import logging
from pathlib import Path

from trendpulse.importers.base import find_files, map_columns, num, read_rows
from trendpulse.importers.gsc import _file_date
from trendpulse.keywords import normalize, valid_candidate
from trendpulse.storage import Store
from trendpulse.types import Observation

log = logging.getLogger(__name__)

# GA4 organic-landing-page exports: demand *satisfied* per topic. The landing
# page slug is collapsed into a topic keyword ("/en/cards/personal-loan/" →
# "cards personal loan").
PAGE_COLS = ("landing page", "landingpage", "landing page + query string", "page path",
             "pagepath", "page")
SESSION_COLS = ("sessions", "engaged sessions", "engagedsessions")
USER_COLS = ("total users", "totalusers", "users")
DATE_COLS = ("date", "day")


def _slug_to_topic(slug: str) -> str:
    slug = slug.split("?")[0].split("#")[0].strip("/")
    parts = [p for p in slug.split("/") if p and len(p) != 2]  # drop locale segments
    return normalize(" ".join(parts[-3:]).replace("-", " ").replace("_", " "))


def import_ga4(store: Store, cfg: dict) -> int:
    directory = Path(cfg.get("imports", {}).get("ga4_dir", "data_imports/ga4"))
    files = find_files(directory, ["*.csv", "*.tsv", "*.xlsx", "*.xls"])
    if not files:
        log.info("[ga4] no files in %s — skipping", directory)
        return 0

    obs: list[Observation] = []
    for path in files:
        rows, headers = read_rows(path)
        mapping = map_columns(headers, {
            "page": PAGE_COLS, "date": DATE_COLS,
            "sessions": SESSION_COLS, "users": USER_COLS,
        })
        if "page" not in mapping or "sessions" not in mapping:
            log.debug("[ga4] %s lacks page/sessions columns — skipped", path.name)
            continue
        for idx, row in enumerate(rows):
            topic = _slug_to_topic(str(row.get(mapping["page"], "")))
            if not valid_candidate(topic):
                continue
            date = (str(row.get(mapping["date"], "")).strip()[:10]
                    if "date" in mapping else _file_date(path, idx, len(rows)))
            obs.append(Observation(
                date=date, keyword=topic, source="ga4", metric="organic_sessions",
                value=num(row[mapping["sessions"]]), region="", language="",
                raw={"page": str(row.get(mapping["page"], ""))[:200]},
            ))
    written = store.upsert_observations(obs)
    log.info("[ga4] imported %d observations from %d files", written, len(files))
    return written
