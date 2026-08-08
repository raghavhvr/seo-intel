"""Self-contained HTML dashboard for non-technical readers.

Rendered from the same database the markdown report uses, written next to it on
every daily run, and additionally to docs/index.html so GitHub Pages can serve
it as a live URL (Settings → Pages → deploy from branch → /docs). Everything is
inline — no CDN scripts, no external fonts — so the file works opened from disk,
attached to an email, or hosted anywhere.

The audience is an SEO/content team, not engineers: every section leads with
what to do, numbers carry plain-language framing, and the only chart forms used
are ranked bars and score bars — no axes to decode.
"""
from __future__ import annotations

import html
import logging
from datetime import date as _date
from datetime import datetime, timezone
from pathlib import Path

from trendpulse.gaps import citation_gaps, citation_summary
from trendpulse.keywords import CHANNELS
from trendpulse.seasonality import upcoming_events
from trendpulse.storage import Store

log = logging.getLogger(__name__)

HORIZON_TITLES = {"week": "This week", "month": "This month", "quarter": "This quarter"}
CHANNEL_BLURBS = {
    "seo": ("SEO — classic search",
            "Queries people type into Google. Create or refresh pages for the top ones."),
    "aeo": ("AEO — answer engines",
            "Question-style queries. Add a 40–60 word direct answer + FAQ schema to win "
            "featured snippets and voice results."),
    "geo": ("GEO — AI assistants",
            "Topics where ChatGPT, Gemini and AI Overviews shape the story. Publish "
            "citable, stat-backed explainers so AI engines reference the bank."),
}

# Colors from the validated reference palette (light mode, committed look).
CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; margin: 0; }
body { background: #f4f4f2; color: #0b0b0b; font: 15px/1.55 -apple-system,
       "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; padding: 32px 16px; }
.wrap { max-width: 1060px; margin: 0 auto; }
h1 { font-size: 26px; letter-spacing: -0.02em; }
h2 { font-size: 19px; margin: 40px 0 4px; letter-spacing: -0.01em; }
h3 { font-size: 15px; margin: 18px 0 8px; }
.sub { color: #52514e; font-size: 13px; }
.note { color: #52514e; font-size: 13px; margin-bottom: 14px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 12px; margin-top: 20px; }
.kpi { background: #fcfcfb; border: 1px solid #e4e3df; border-radius: 10px;
       padding: 16px 18px; }
.kpi .v { font-size: 28px; font-weight: 650; letter-spacing: -0.02em; }
.kpi .l { color: #52514e; font-size: 12.5px; margin-top: 2px; }
.card { background: #fcfcfb; border: 1px solid #e4e3df; border-radius: 10px;
        padding: 18px 20px; margin-top: 10px; overflow-x: auto; }
.bar-row { display: grid; grid-template-columns: 190px 1fr 84px; gap: 10px;
           align-items: center; padding: 5px 0; }
.bar-row .name { font-size: 13.5px; white-space: nowrap; overflow: hidden;
                 text-overflow: ellipsis; }
.bar-track { background: #eceae6; border-radius: 4px; height: 14px; }
.bar-fill { height: 14px; border-radius: 4px; min-width: 2px; }
.bar-val { font-size: 12.5px; color: #52514e; text-align: right;
           font-variant-numeric: tabular-nums; }
.you { font-weight: 650; }
.badge { display: inline-block; font-size: 11px; font-weight: 600; padding: 1px 7px;
         border-radius: 999px; margin-left: 6px; vertical-align: 1px; }
.b-you { background: #e3edfa; color: #17559c; }
.b-breakout { background: #fdeade; color: #a53c12; }
.b-rising { background: #e2f4ec; color: #0c6b4a; }
.b-cooling { background: #eceae6; color: #52514e; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
th { text-align: left; color: #52514e; font-weight: 600; font-size: 12px;
     padding: 6px 10px 6px 0; border-bottom: 1px solid #e4e3df; }
td { padding: 7px 10px 7px 0; border-bottom: 1px solid #efeeea;
     vertical-align: top; }
td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.scorebar { display: inline-block; height: 8px; border-radius: 4px;
            background: #2a78d6; vertical-align: 2px; margin-right: 7px; }
.cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        gap: 12px; }
ol.gaps { padding-left: 20px; }
ol.gaps li { margin: 10px 0; }
ol.gaps .who { color: #52514e; font-size: 12.5px; }
.moment { display: grid; grid-template-columns: 120px 1fr; gap: 12px;
          padding: 8px 0; border-bottom: 1px solid #efeeea; font-size: 13.5px; }
.moment:last-child { border-bottom: 0; }
.moment .when { color: #52514e; font-variant-numeric: tabular-nums; }
footer { color: #52514e; font-size: 12px; margin-top: 40px; }
@media (max-width: 640px) { .bar-row { grid-template-columns: 120px 1fr 64px; } }
"""


def _esc(text) -> str:
    return html.escape(str(text))


def _bar_rows(rows, *, unit: str = "", highlight=None) -> str:
    """Ranked horizontal bars: (name, value, is_you). Direct-labeled, brand in
    blue, everyone else neutral — color marks the entity's role, not its rank."""
    top = max((v for _n, v, _y in rows), default=1.0) or 1.0
    out = []
    for name, value, is_you in rows:
        width = max(100.0 * value / top, 1.5)
        color = "#2a78d6" if is_you else "#b3b1ab"
        you = ' <span class="badge b-you">you</span>' if is_you else ""
        cls = "name you" if is_you else "name"
        out.append(
            f'<div class="bar-row"><div class="{cls}" title="{_esc(name)}">{_esc(name)}{you}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%;'
            f'background:{color}"></div></div>'
            f'<div class="bar-val">{value:,.0f}{unit}</div></div>')
    return "".join(out)


def _momentum_badge(delta: float, breakout: bool) -> str:
    if breakout:
        return '<span class="badge b-breakout">act now</span>'
    if delta > 0.15:
        return '<span class="badge b-rising">rising</span>'
    if delta < -0.15:
        return '<span class="badge b-cooling">cooling</span>'
    return ""


def _focus_table(rows) -> str:
    """(keyword, score, delta, velocity) → an exec-readable ranked table."""
    if not rows:
        return '<p class="note">No signals yet.</p>'
    body = []
    for rank, (keyword, score, delta, _vel) in enumerate(rows, 1):
        body.append(
            f"<tr><td class=\"num\">{rank}</td>"
            f"<td>{_esc(keyword)} {_momentum_badge(delta, False)}</td>"
            f"<td class=\"num\"><span class=\"scorebar\" style=\"width:{max(score, 2) * 0.55:.0f}px\"></span>"
            f"{score:.0f}</td></tr>")
    return ("<table><tr><th>#</th><th>Query / topic</th><th>Priority score</th></tr>"
            + "".join(body) + "</table>")


def generate_dashboard(store: Store, cfg: dict, out_dir: Path,
                       extra_paths: list[Path] | None = None) -> Path:
    cur = store.conn.execute("SELECT MAX(date) FROM scores")
    score_date = (cur.fetchone() or [None])[0]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    visibility = store.entity_visibility(days=7)
    summary = citation_summary(store, cfg, days=30)
    gaps = citation_gaps(store, cfg, days=30, limit=8)
    events = upcoming_events(cfg, _date.today(), within_days=90)
    n_keywords = store.conn.execute(
        "SELECT COUNT(DISTINCT keyword) FROM scores WHERE date = ?",
        (score_date,)).fetchone()[0] if score_date else 0

    brand_sov = next((sov for _e, kind, _c, sov in visibility if kind == "brand"), None)
    own_citation = next((share for _d, _c, share, role in summary if role == "own"), None)
    top_pick = None
    if score_date:
        top = store.latest_scores(score_date, "week", "seo", limit=1)
        top_pick = top[0][0] if top else None

    parts: list[str] = []
    parts.append(f"<h1>{_esc(cfg.get('project', 'TrendPulse'))} — trend dashboard</h1>")
    parts.append(f'<p class="sub">Market: {_esc(cfg.get("market", ""))} · data through '
                 f'{_esc(score_date or "—")} · regenerated automatically every morning '
                 f'({_esc(generated)})</p>')

    parts.append('<div class="kpis">')
    for value, label in [
        (f"{brand_sov:.1f}%" if brand_sov is not None else "—",
         "share of voice when AI assistants & communities talk about UAE banks (7 days)"),
        (f"{own_citation:.1f}%" if own_citation is not None else "—",
         "of AI-engine citations for banking prompts go to adcb.com (30 days)"),
        (f"{n_keywords:,}", "queries & topics tracked and scored daily"),
        (_esc(top_pick) if top_pick else "—", "single top search opportunity this week"),
    ]:
        parts.append(f'<div class="kpi"><div class="v">{value}</div>'
                     f'<div class="l">{label}</div></div>')
    parts.append("</div>")

    if visibility:
        parts.append("<h2>Who owns the conversation?</h2>")
        parts.append('<p class="note">Mentions of each bank across AI-assistant answers '
                     "(ChatGPT, Gemini, Perplexity, AI Overviews) and community chatter "
                     "(Reddit, news) in the last 7 days. Each sighting counts once.</p>")
        rows = [(e, c, kind == "brand") for e, kind, c, _s in visibility[:10]]
        parts.append(f'<div class="card">{_bar_rows(rows)}</div>')

    if summary:
        parts.append("<h2>Who do AI engines cite for banking questions?</h2>")
        parts.append('<p class="note">When AI assistants answer banking &amp; finance '
                     "prompts, these are the websites they link as sources (last 30 days). "
                     "More citations → more presence inside AI answers.</p>")
        own = {d for d, _c, _s, r in summary if r == "own"}
        rows = [(d, c, d in own) for d, c, _share, _r in summary[:10]]
        parts.append(f'<div class="card">{_bar_rows(rows)}</div>')

    if gaps:
        parts.append("<h2>Content to publish next — the citation gaps</h2>")
        parts.append('<p class="note">Real questions people asked AI assistants where the '
                     "answer cited other banks but never adcb.com. Publishing a clear, "
                     "citable page for each is the fastest way to enter those answers.</p>")
        items = []
        for gap in gaps:
            items.append(f"<li><strong>{_esc(gap['prompt'])}</strong><br>"
                         f'<span class="who">currently cited: '
                         f"{_esc(', '.join(gap['domains'][:4]))} — asked on "
                         f"{_esc(', '.join(gap['models'][:4]))}</span></li>")
        parts.append(f'<div class="card"><ol class="gaps">{"".join(items)}</ol></div>')

    if score_date:
        for horizon in cfg["model"]["horizons"]:
            parts.append(f"<h2>Focus queries — {HORIZON_TITLES.get(horizon, horizon).lower()}</h2>")
            parts.append('<p class="note">Ranked by predicted growth in attention across '
                         "all sources. Score is a percentile (100 = strongest signal today).</p>")
            parts.append('<div class="cols">')
            for channel in CHANNELS:
                title, blurb = CHANNEL_BLURBS[channel]
                rows = store.latest_scores(score_date, horizon, channel, limit=8)
                parts.append(f'<div class="card"><h3>{_esc(title)}</h3>'
                             f'<p class="note">{_esc(blurb)}</p>{_focus_table(rows)}</div>')
            parts.append("</div>")

    if events:
        parts.append("<h2>Upcoming regional moments</h2>")
        parts.append('<p class="note">Content must rank <em>before</em> the moment, '
                     "not during it. Dates marked ~ follow the Hijri calendar — verify "
                     "before publishing.</p>")
        rows = []
        for event in events:
            approx = "~" if event.expected else ""
            when = f"{approx}{event.start:%d %b %Y}"
            action = f" — {_esc(event.action)}" if event.action else ""
            rows.append(f'<div class="moment"><div class="when">{when}</div>'
                        f"<div><strong>{_esc(event.name)}</strong>{action}</div></div>")
        parts.append(f'<div class="card">{"".join(rows)}</div>')

    parts.append("<footer>Sources: Google Trends, Google Autocomplete, Google News, "
                 "Wikipedia, Reddit, Stack Exchange, Hacker News, arXiv, Hugging Face, "
                 "NASA EONET, TryProfound (AI answers), Google Search Console + GA4 "
                 "imports. Scores are directional decision-support — validate big bets "
                 "against Search Console. Full details: reports/latest.md in the "
                 "repository.</footer>")

    page = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{_esc(cfg.get('project', 'TrendPulse'))} — trend dashboard</title>"
            f"<style>{CSS}</style></head><body><div class=\"wrap\">"
            + "".join(parts) + "</div></body></html>")

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "dashboard.html"
    path.write_text(page, encoding="utf-8")
    for extra in extra_paths or []:
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text(page, encoding="utf-8")
    log.info("dashboard written to %s", path)
    return path
