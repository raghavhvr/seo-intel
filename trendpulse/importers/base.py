from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)


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


def _parse_csv_text(text: str) -> tuple[list[dict], list[str]]:
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = list(reader)
    return rows, list(reader.fieldnames or [])


def read_rows(path: Path) -> tuple[list[dict], list[str]]:
    """CSV (any delimiter via sniffer, UTF-8 BOM tolerant) or Excel via pandas."""
    if path.suffix.lower() in (".xlsx", ".xls"):
        import pandas as pd

        frame = pd.read_excel(path)
        return frame.to_dict("records"), [str(c) for c in frame.columns]
    return _parse_csv_text(path.read_text(encoding="utf-8-sig", errors="replace"))


def iter_tables(path: Path):
    """Yield (display_name, rows, headers) for every table a file holds.

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
                rows, headers = _parse_csv_text(text)
                yield f"{path.name}/{member}", rows, headers
        return
    rows, headers = read_rows(path)
    yield path.name, rows, headers


def num(value) -> float:
    try:
        return float(str(value).replace(",", "").replace("%", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0
