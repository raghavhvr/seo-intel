"""Audit: is each source pulling data that is relevant to the ADCB universe?

Usage: python scripts/audit_sources.py [db-path]
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict

db = sys.argv[1] if len(sys.argv) > 1 else "data/trendpulse.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

print("=" * 78)
print("PER-SOURCE COVERAGE (observations, keywords covered, zero-signal rate)")
print("=" * 78)
rows = conn.execute(
    "SELECT source, metric, region, language, keyword, value"
    " FROM observations WHERE source != 'synthetic'"
).fetchall()

by_source: dict[str, list] = defaultdict(list)
for r in rows:
    by_source[r["source"]].append(r)

for source in sorted(by_source):
    items = by_source[source]
    kws = {r["keyword"] for r in items}
    regions = sorted({r["region"] for r in items if r["region"]})
    langs = sorted({r["language"] for r in items if r["language"]})
    zero = sum(1 for r in items if r["value"] == 0)
    print(f"\n{source}: {len(items)} obs | {len(kws)} keywords | "
          f"{100 * zero / max(len(items), 1):.0f}% zero-value")
    print(f"  regions: {regions or '-'} | languages: {langs or '-'}")
    metrics = defaultdict(list)
    for r in items:
        metrics[r["metric"]].append(r["value"])
    for metric, values in metrics.items():
        nz = [v for v in values if v > 0]
        print(f"  {metric}: mean={sum(values) / len(values):.1f}, "
              f"non-zero={len(nz)}/{len(values)}")

print()
print("=" * 78)
print("SEED COVERAGE MATRIX (which seeds got real signal, from which sources)")
print("=" * 78)
seeds = conn.execute(
    "SELECT DISTINCT keyword FROM observations WHERE source != 'discovery'"
).fetchall()
matrix = defaultdict(set)
for r in rows:
    if r["value"] > 0:
        matrix[r["keyword"]].add(r["source"])
for (kw,) in sorted(seeds, key=lambda x: x[0]):
    srcs = sorted(matrix.get(kw, set()))
    flag = "" if srcs else "  <-- NO SIGNAL ANYWHERE"
    print(f"  {kw[:45]:47s} {len(srcs)} sources: {', '.join(srcs)}{flag}")

print()
print("=" * 78)
print("DISCOVERY SAMPLES PER SOURCE (would these matter to a UAE bank?)")
print("=" * 78)
discs = conn.execute(
    "SELECT source, keyword, context, score FROM discoveries"
    " ORDER BY source, score DESC"
).fetchall()
by_src = defaultdict(list)
for d in discs:
    by_src[d["source"]].append(d)
for source in sorted(by_src):
    items = by_src[source]
    print(f"\n{source} ({len(items)} discoveries):")
    for d in items[:6]:
        print(f"  [{d['score']:6.1f}] {d['keyword'][:60]}")
        print(f"           <- {d['context'][:90]}")
conn.close()
