from __future__ import annotations

import csv
import logging
import re
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


def read_rows(path: Path) -> tuple[list[dict], list[str]]:
    """CSV (any delimiter via sniffer, UTF-8 BOM tolerant) or Excel via pandas."""
    if path.suffix.lower() in (".xlsx", ".xls"):
        import pandas as pd

        frame = pd.read_excel(path)
        return frame.to_dict("records"), [str(c) for c in frame.columns]
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        rows = list(reader)
        return rows, list(reader.fieldnames or [])


def num(value) -> float:
    try:
        return float(str(value).replace(",", "").replace("%", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0
