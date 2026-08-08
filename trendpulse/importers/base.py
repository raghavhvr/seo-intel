from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from pathlib import Path
from typing import NamedTuple

log = logging.getLogger(__name__)

# An 8 MB GA4 export with one stray quote overflows csv's default 128 KB field
# cap ("_csv.Error: field larger than field limit"). sys.maxsize overflows a C
# long on Windows, so use a plain large constant.
csv.field_size_limit(10_000_000)


class Table(NamedTuple):
    name: str          # archive-qualified display name, carries export window
    rows: list[dict]
    headers: list[str]
    preamble: str      # leading '# …' comment block (GA4 keeps its date range here)


def find_files(directory: str | Path, patterns: list[str]) -> list[Path]:
    base = Path(directory)
    if not base.exists():
        return []
    out: list[Path] = []
    for pattern in patterns:
        out.extend(sorted(base.rglob(pattern)))
    return sorted(set(p for p in out if p.is_file()))


def _canon(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", header.strip().lower())


def map_columns(fieldnames: list[str], spec: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """Map canonical logical fields to actual CSV headers (case/format tolerant)."""
    lookup = {_canon(name): name for name in fieldnames}
    mapping: dict[str, str] = {}
    for logical, aliases in spec.items():
        for alias in aliases:
            if _canon(alias) in lookup:
                mapping[logical] = lookup[_canon(alias)]
                break
    return mapping


def _parse_csv_text(text: str) -> tuple[list[dict], list[str], str]:
    # GA4's UI exports open with a comment preamble ('# All Users', '# 2026…')
    # before the real header row. Without stripping it, the first comment line
    # becomes the header, no expected column matches, and the file silently
    # imports zero rows. The preamble is kept — GA4 hides the export's date
    # range in it ('# 20251001-20260228'), which the importer needs to turn a
    # bare Month column into real dates.
    lines = text.splitlines()
    start = 0
    while start < len(lines) and (not lines[start].strip()
                                  or lines[start].lstrip().startswith("#")):
        start += 1
    preamble = "\n".join(lines[:start])
    text = "\n".join(lines[start:])
    # Delimiter only — csv.Sniffer's full-dialect guessing misfires on real
    # GA4 exports (a wrongly inferred quote rule swallowed megabytes into one
    # "field" and crashed the run). Count candidates in the header line.
    header = text.split("\n", 1)[0]
    delimiter = max(",;\t", key=header.count)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    return rows, list(reader.fieldnames or []), preamble


def read_rows(path: Path) -> tuple[list[dict], list[str]]:
    """CSV (delimiter auto-detected, UTF-8 BOM tolerant) or Excel via pandas."""
    if path.suffix.lower() in (".xlsx", ".xls"):
        import pandas as pd

        frame = pd.read_excel(path)
        return frame.to_dict("records"), [str(c) for c in frame.columns]
    rows, headers, _pre = _parse_csv_text(path.read_text(encoding="utf-8-sig",
                                                         errors="replace"))
    return rows, headers


def iter_tables(path: Path):
    """Yield a Table for every table a file holds.

    Plain CSV/Excel files yield themselves once. Zip archives (what the GSC UI
    actually hands you — Queries.csv, Pages.csv, Countries.csv, … bundled) are
    read in place, one yield per member, so exports can be dropped in exactly
    as downloaded. The display name keeps the archive's own filename first
    because that's where the export window lives ('…-Jul-26.zip'); members
    without a usable column set are the caller's job to skip."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            for member in sorted(zf.namelist()):
                if member.endswith("/") or not member.lower().endswith((".csv", ".tsv")):
                    continue
                text = zf.read(member).decode("utf-8-sig", errors="replace")
                rows, headers, preamble = _parse_csv_text(text)
                yield Table(f"{path.name}/{member}", rows, headers, preamble)
        return
    if path.suffix.lower() in (".xlsx", ".xls"):
        rows, headers = read_rows(path)
        yield Table(path.name, rows, headers, "")
        return
    rows, headers, preamble = _parse_csv_text(
        path.read_text(encoding="utf-8-sig", errors="replace"))
    yield Table(path.name, rows, headers, preamble)


_YMD = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


def iso_date(value) -> str:
    """Normalize a row's date cell to YYYY-MM-DD. GA4 exports write dates as
    bare '20260301'; stored verbatim they'd sit alongside '2026-03-01' keys
    from every other source and split one day into two."""
    text = str(value).strip()
    match = _YMD.match(text)
    if match:
        return "-".join(match.groups())
    return text[:10]


def num(value) -> float:
    try:
        return float(str(value).replace(",", "").replace("%", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0
