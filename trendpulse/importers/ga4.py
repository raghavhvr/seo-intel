from __future__ import annotations

import calendar
import logging
import re
from pathlib import Path

from trendpulse.importers.base import (find_files, iso_date, iter_tables,
                                       map_columns, num)
from trendpulse.importers.gsc import _file_date
from trendpulse.keywords import normalize, valid_candidate
from trendpulse.storage import Store
from trendpulse.types import Observation

log = logging.getLogger(__name__)

# GA4 organic-landing-page exports: demand *satisfied* per topic. The landing
# page slug is collapsed into a topic keyword ("/en/cards/personal-loan/" →
# "cards personal loan").
#
# The real "Free form" export (verified against ADCB samples) is monthly and
# multi-dimensional: a bare `Month` column ('10', '01' — the year lives only in
# the '# 20251001-20260228' comment preamble, and the range can cross a year
# boundary), one row per page × channel group × source/medium, plus a trailing
# 'Grand total' row. Daily exports with a proper Date column also work.
PAGE_COLS = ("landing page", "landingpage", "landing page + query string", "page path",
             "pagepath", "page", "page location")
SESSION_COLS = ("sessions", "engaged sessions", "engagedsessions")
USER_COLS = ("total users", "totalusers", "users")
DATE_COLS = ("date", "day")
MONTH_COLS = ("month",)
CHANNEL_COLS = ("session default channel group", "default channel group",
                "channel group", "channel")

RANGE_RE = re.compile(r"(\d{8})-(\d{8})")


def _slug_to_topic(slug: str) -> str:
    slug = slug.split("?")[0].split("#")[0].strip("/")
    parts = [p for p in slug.split("/") if p and len(p) != 2]  # drop locale segments
    return normalize(" ".join(parts[-3:]).replace("-", " ").replace("_", " "))


def _month_dater(preamble: str):
    """Turn GA4's bare Month column into YYYY-MM-<last day>, inferring the year
    from the export range in the '#' preamble. Returns None without a range."""
    match = RANGE_RE.search(preamble)
    if not match:
        return None
    y0, m0 = int(match.group(1)[:4]), int(match.group(1)[4:6])

    def dater(month_value: str) -> str | None:
        try:
            mon = int(str(month_value).strip())
        except (TypeError, ValueError):
            return None
        if not 1 <= mon <= 12:
            return None
        year = y0 if mon >= m0 else y0 + 1  # an Oct→Feb export crosses the year
        return f"{year:04d}-{mon:02d}-{calendar.monthrange(year, mon)[1]:02d}"

    return dater


def import_ga4(store: Store, cfg: dict) -> int:
    directory = Path(cfg.get("imports", {}).get("ga4_dir", "data_imports/ga4"))
    files = find_files(directory, ["*.csv", "*.tsv", "*.xlsx", "*.xls", "*.zip"])
    if not files:
        log.info("[ga4] no files in %s — skipping", directory)
        return 0

    # Rows are per page × channel × source/medium, so sessions must be SUMMED
    # per (date, topic) — an upsert per raw row would keep only the last
    # channel's number for each key.
    totals: dict[tuple[str, str], float] = {}
    pages: dict[tuple[str, str], str] = {}
    for path in files:
        for name, rows, headers, preamble in iter_tables(path):
            mapping = map_columns(headers, {
                "page": PAGE_COLS, "date": DATE_COLS, "month": MONTH_COLS,
                "sessions": SESSION_COLS, "users": USER_COLS,
                "channel": CHANNEL_COLS,
            })
            if "page" not in mapping or "sessions" not in mapping:
                log.debug("[ga4] %s lacks page/sessions columns — skipped", name)
                continue
            month_to_date = _month_dater(preamble) if "month" in mapping else None
            for idx, row in enumerate(rows):
                page = str(row.get(mapping["page"], ""))
                if "grand total" in page.lower():
                    continue
                topic = _slug_to_topic(page)
                if not valid_candidate(topic):
                    continue
                # Organic only, when the export breaks rows out by channel:
                # paid/direct/referral sessions are not search demand.
                if "channel" in mapping:
                    channel = str(row.get(mapping["channel"], "")).lower()
                    if "organic" not in channel:
                        continue
                if "date" in mapping:
                    date = iso_date(row.get(mapping["date"], ""))
                elif month_to_date is not None:
                    date = month_to_date(row.get(mapping["month"]))
                    if date is None:
                        continue  # 'Grand total' and other non-month rows
                else:
                    date = _file_date(name, idx, len(rows))
                key = (date, topic)
                totals[key] = totals.get(key, 0.0) + num(row[mapping["sessions"]])
                pages.setdefault(key, page[:200])

    obs = [Observation(date=date, keyword=topic, source="ga4",
                       metric="organic_sessions", value=value,
                       region="", language="", raw={"page": pages[(date, topic)]})
           for (date, topic), value in totals.items()]
    written = store.upsert_observations(obs)
    log.info("[ga4] imported %d observations from %d files", written, len(files))
    return written
