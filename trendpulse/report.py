from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from trendpulse.features import build_snapshot, keyword_attention
from trendpulse.keywords import CHANNELS, channels_for
from trendpulse.model import HorizonModel
from trendpulse.scoring import is_breakout, stat_projected_delta
from trendpulse.storage import Store

log = logging.getLogger(__name__)

HORIZON_TITLES = {"week": "This week", "month": "This month", "quarter": "This quarter"}

ACTIONS = {
    "seo": "Create/refresh a dedicated page targeting this query; interlink from related pages.",
    "aeo": "Add a concise 40–60 word direct answer; mark up with FAQPage/HowTo schema; target voice/featured snippets.",
    "geo": "Publish a definitive, stat-backed explainer with clear entity references, citations-friendly formatting, and up-to-date facts so AI engines cite you.",
}


def _action(channels: set[str], breakout: bool) -> str:
    parts = []
    if "geo" in channels:
        parts.append(ACTIONS["geo"])
    if "aeo" in channels:
        parts.append(ACTIONS["aeo"])
    parts.append(ACTIONS["seo"])
    if breakout:
        parts.insert(0, "BREAKOUT detected — act now while competition is low.")
    return " ".join(parts)


def score_keywords(store: Store, cfg: dict, universe: dict[str, str | None],
                   models: dict[str, HorizonModel]) -> pd.DataFrame:
    """Score every keyword for every horizon. Uses ML predictions where a
    trained model exists, otherwise the statistical projection."""
    snapshot = build_snapshot(store, cfg, universe)
    if snapshot.empty:
        return snapshot

    attention = keyword_attention(store, universe)
    horizons = {h: int(d) for h, d in cfg["model"]["horizons"].items()}
    frame = snapshot.set_index("keyword")

    for horizon, days in horizons.items():
        model = models.get(horizon)
        if model is not None:
            frame[f"delta_{horizon}"] = model.predict(frame.reset_index(drop=True))
        else:
            frame[f"delta_{horizon}"] = [
                stat_projected_delta(attention[kw][0], days) if kw in attention else 0.0
                for kw in frame.index
            ]

    for horizon in horizons:
        raw = (frame[f"delta_{horizon}"].clip(-3, 3)
               + 0.5 * frame["velocity_z"].clip(-3, 3)
               + 0.25 * frame["breadth7"].clip(0, 6))
        span = float(raw.max() - raw.min()) or 1.0
        frame[f"score_{horizon}"] = (100 * (raw - raw.min()) / span).round(1)

    frame["channels"] = [
        sorted(channels_for(kw, cfg, universe.get(kw))) for kw in frame.index
    ]
    frame["breakout"] = [
        is_breakout(attention[kw][0]) if kw in attention else False for kw in frame.index
    ]
    frame["as_of"] = str(frame["date"].iloc[0]) if "date" in frame else ""
    return frame.reset_index()


def _evidence(store: Store, keyword: str) -> str:
    items = store.recent_discoveries(keyword, days=30, limit=3)
    return " | ".join(f"{date}: {context[:110]}" for date, context, _s in items)


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def generate_report(store: Store, cfg: dict, universe: dict[str, str | None],
                    models: dict[str, HorizonModel]) -> Path:
    scored = score_keywords(store, cfg, universe, models)
    out_dir = Path(cfg["reports"]["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    top_n = int(cfg["reports"]["top_n"])
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    horizons = list(cfg["model"]["horizons"].keys())
    using_ml = {h: h in models for h in horizons}

    lines: list[str] = []
    lines.append(f"# Trend report — {cfg.get('project', 'TrendPulse')}")
    lines.append("")
    market = cfg.get("market")
    regions = ", ".join(cfg.get("regions") or [cfg.get("region", "US")])
    lines.append(f"Generated {date} (UTC)"
                 + (f" · market: {market}" if market else "")
                 + f" · regions: {regions} · keywords tracked: {len(scored)} · "
                 f"scoring: {'ML model' if any(using_ml.values()) else 'statistical (ML activates after ~6–8 weeks of daily data)'}")
    lines.append("")

    from datetime import date as _date

    from trendpulse.seasonality import upcoming_events

    events = upcoming_events(cfg, _date.today(), within_days=90)
    if events:
        lines.append("## Upcoming regional moments (next 90 days)")
        lines.append("")
        for event in events:
            if event.is_active(_date.today()):
                status = "ACTIVE NOW"
            elif event.in_prep_window(_date.today()):
                status = f"starts in {event.days_until(_date.today())}d — prep window is NOW"
            else:
                status = f"starts in {event.days_until(_date.today())}d"
            approx = " (expected date — verify)" if event.expected else ""
            lines.append(f"- **{event.name}**{approx} — {status}"
                         + (f" [{', '.join(event.regions)}]" if event.regions else ""))
            if event.action:
                lines.append(f"  - {event.action}")
            if event.keywords:
                lines.append(f"  - Keyword angles: {', '.join(event.keywords)}")
        lines.append("")

    for horizon in horizons:
        lines.append(f"## {HORIZON_TITLES.get(horizon, horizon)}")
        lines.append("")
        score_col, delta_col = f"score_{horizon}", f"delta_{horizon}"
        for channel in CHANNELS:
            subset = scored[scored["channels"].apply(lambda cs: channel in cs)]
            subset = subset.sort_values(score_col, ascending=False).head(top_n)
            lines.append(f"### {channel.upper()} — top {len(subset)}")
            lines.append("")
            if subset.empty:
                lines.append("_No signals yet._")
                lines.append("")
                continue
            lines.append("| # | Keyword / query | Score | Predicted momentum | Velocity (z) | Signals |")
            lines.append("|---|-----------------|-------|--------------------|--------------|---------|")
            csv_rows: list[dict] = []
            for rank, (_, row) in enumerate(subset.iterrows(), 1):
                delta = float(row[delta_col])
                direction = "rising" if delta > 0.15 else ("cooling" if delta < -0.15 else "steady")
                signals = []
                if row["breakout"]:
                    signals.append("breakout")
                if row["is_question"]:
                    signals.append("question")
                if row["ch_geo"]:
                    signals.append("ai-topic")
                sig = ", ".join(signals) or "—"
                lines.append(
                    f"| {rank} | {row['keyword']} | {row[score_col]:.0f} | "
                    f"{direction} ({delta:+.2f}) | {row['velocity_z']:+.2f} | {sig} |"
                )
                csv_rows.append({
                    "rank": rank, "keyword": row["keyword"], "channel": channel,
                    "horizon": horizon, "trend_score": round(float(row[score_col]), 1),
                    "predicted_delta": round(delta, 3),
                    "velocity_z": round(float(row["velocity_z"]), 3),
                    "breakout": bool(row["breakout"]),
                    "evidence": _evidence(store, row["keyword"]),
                    "suggested_action": _action(set(row["channels"]), bool(row["breakout"])),
                })
                store.save_score(date, row["keyword"], horizon, channel,
                                 float(row[score_col]), delta, float(row["velocity_z"]))
            lines.append("")
            _write_csv(out_dir / f"{date}-{horizon}-{channel}.csv", csv_rows)

        # Deep dive on the very top picks across channels
        top_overall = scored.sort_values(score_col, ascending=False).head(5)
        lines.append(f"#### Deep dive — top {len(top_overall)} picks ({horizon})")
        lines.append("")
        for _, row in top_overall.iterrows():
            lines.append(f"- **{row['keyword']}** ({', '.join(row['channels'])}) — "
                         f"{_action(set(row['channels']), bool(row['breakout']))}")
            evidence = _evidence(store, row["keyword"])
            if evidence:
                lines.append(f"  - Evidence: {evidence}")
        lines.append("")

    from trendpulse.keywords import is_relevant, universe_tokens

    tokens = universe_tokens(universe)
    new_this_week = [
        (kw, s) for kw, s in sorted(store.discovered_keywords(limit=400),
                                    key=lambda kv: kv[1], reverse=True)
        if is_relevant(kw, tokens, cfg)
    ][:15]
    if new_this_week:
        lines.append("## Newly discovered queries & topics (related to your universe)")
        lines.append("")
        for kw, s in new_this_week:
            lines.append(f"- {kw} (discovery score {s:.0f})")
        lines.append("")

    # --- GEO citation gaps: who AI engines cite for banking prompts --------
    from trendpulse.gaps import citation_gaps, citation_summary

    summary = citation_summary(store, cfg, days=30)
    if summary:
        lines.append("## GEO citation share (last 30 days · TryProfound)")
        lines.append("")
        lines.append("Domains AI engines cite most for banking & finance prompts:")
        lines.append("")
        lines.append("| Domain | Citations | Share | |")
        lines.append("|--------|-----------|-------|---|")
        for domain, count, share, role in summary[:12]:
            tag = {"own": "**← you**", "competitor": "competitor", "other": ""}[role]
            lines.append(f"| {domain} | {count} | {share:.1f}% | {tag} |")
        lines.append("")

        gaps = citation_gaps(store, cfg, days=30, limit=10)
        if gaps:
            lines.append("### Citation gaps — prompts where AI cites others, not you")
            lines.append("")
            lines.append("This is your GEO content backlog: pages to publish or "
                         "reshape so AI engines can cite them.")
            lines.append("")
            for rank, gap in enumerate(gaps, 1):
                lines.append(
                    f"{rank}. **{gap['prompt']}** — cited: "
                    f"{', '.join(gap['domains'])} ({', '.join(gap['models'])})")
                lines.append(
                    "   → Publish/refresh a page that directly answers this; mirror "
                    "what cited pages do well (clear answer up top, rates/table, FAQ schema).")
            lines.append("")

    # --- Brand share-of-voice: AI answers (Profound) + community chatter ---
    visibility = store.entity_visibility(days=7)
    if visibility:
        lines.append("## Brand share of voice (last 7 days)")
        lines.append("")
        lines.append("AI-answer mentions (TryProfound) plus community chatter "
                     "(Reddit / news / HN discoveries mentioning the entities).")
        lines.append("")
        lines.append("| Entity | Type | Mentions | Share of voice |")
        lines.append("|--------|------|----------|----------------|")
        for entity, kind, count, sov in visibility:
            lines.append(f"| {entity} | {kind} | {count:.0f} | {sov:.1f}% |")
        lines.append("")
        for entity, kind, _c, _s in visibility:
            if kind != "brand":
                continue
            contexts = store.entity_contexts(entity, days=30, limit=3)
            if contexts:
                lines.append(f"Where **{entity}** shows up:")
                for d, source, context in contexts:
                    lines.append(f"- {d} · {source}: {context}")
                lines.append("")

    lines.append("---")
    lines.append("Horizons: week = 7 days, month = 30 days, quarter = 90 days. "
                 "Scores are percentile-ranked within this run; predicted momentum is the "
                 "expected change in blended cross-source attention.")
    store.conn.commit()

    report_path = out_dir / f"{date}.md"
    report_path.write_text("\n".join(lines))
    (out_dir / "latest.md").write_text("\n".join(lines))
    log.info("report written to %s", report_path)
    return report_path
