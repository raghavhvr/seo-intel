"""Self-contained HTML dashboard for non-technical readers.

Rendered from the same database the markdown report uses, written next to it on
every daily run, and additionally to docs/index.html so GitHub Pages can serve
it as a live URL (Settings → Pages → deploy from branch → /docs). Everything is
inline — no CDN scripts, no external fonts — so the file works opened from disk,
attached to an email, or hosted anywhere.

The audience is an SEO/content team, not engineers: the page opens with the
three actions that matter today, every section leads with what to do, and the
only chart forms used are ranked bars and score bars — no axes to decode.
"""
from __future__ import annotations

import html
import logging
from datetime import date as _date
from datetime import datetime, timezone
from pathlib import Path

from trendpulse.entities import competitor_matcher
from trendpulse.gaps import citation_gaps, citation_summary
from trendpulse.keywords import CHANNELS, channels_for, excluded_keywords
from trendpulse.report import ACTIONS
from trendpulse.seasonality import upcoming_events
from trendpulse.storage import Store

log = logging.getLogger(__name__)

HORIZON_TITLES = {"week": "This week", "month": "This month", "quarter": "This quarter"}
CHANNEL_META = {
    "seo": ("SEO", "Classic search",
            "Queries people type into Google. Create or refresh pages for the top ones."),
    "aeo": ("AEO", "Answer engines",
            "Question-style queries. Add a 40–60 word direct answer + FAQ schema to win "
            "featured snippets and voice results."),
    "geo": ("GEO", "AI assistants",
            "Topics where ChatGPT, Gemini and AI Overviews shape the story. Publish "
            "citable, stat-backed explainers so AI engines reference the bank."),
}

# Colors from the validated reference palette (light mode, committed look).
# Brand rows use the blue pair (AI-answer segment dark, community light);
# everyone else the neutral pair — hue marks the entity's role, never its rank.
CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; margin: 0; }
body { background: #f2f1ee; color: #171715; font: 15px/1.55 -apple-system,
       "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
.hero { background: linear-gradient(135deg, #101d33 0%, #1a3a63 100%);
        color: #fff; padding: 44px 20px 108px; }
.hero .wrap { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 18px; }
.hero h1 { font-size: 27px; letter-spacing: -0.02em; font-weight: 700; }
.hero .tag { color: #b9c6da; font-size: 13px; }
.hero .live { margin-left: auto; font-size: 12px; color: #cfe3ff; background:
              rgba(255,255,255,.1); border: 1px solid rgba(255,255,255,.25);
              padding: 3px 11px; border-radius: 999px; white-space: nowrap; }
.hero .live::before { content: ""; display: inline-block; width: 7px; height: 7px;
              border-radius: 50%; background: #4cd98a; margin-right: 7px; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 0 4px; }
main.wrap { padding-bottom: 56px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(215px, 1fr));
        gap: 14px; margin-top: -64px; }
.kpi { background: #fff; border: 1px solid #e2e0db; border-radius: 14px;
       padding: 18px 20px; box-shadow: 0 8px 22px rgba(16, 29, 51, .07); }
.kpi .v { font-size: 30px; font-weight: 700; letter-spacing: -0.02em; }
.kpi .v small { font-size: 15px; font-weight: 600; color: #52514e; }
.kpi .l { color: #52514e; font-size: 12.5px; margin-top: 3px; line-height: 1.45; }
.kpi .d { font-size: 12px; margin-top: 7px; font-weight: 600; }
.d.up { color: #0c6b4a; } .d.down { color: #a53c12; } .d.flat { color: #52514e; }
.eyebrow { font-size: 11.5px; font-weight: 700; letter-spacing: .12em;
           text-transform: uppercase; color: #17559c; margin: 46px 0 2px; }
h2 { font-size: 21px; letter-spacing: -0.015em; margin: 0 0 4px; }
.note { color: #52514e; font-size: 13.5px; margin-bottom: 14px; max-width: 760px; }
.card { background: #fff; border: 1px solid #e2e0db; border-radius: 14px;
        padding: 20px 22px; margin-top: 12px; overflow-x: auto;
        box-shadow: 0 2px 8px rgba(16, 29, 51, .04); }
.legend { display: flex; gap: 16px; font-size: 12px; color: #52514e; margin-bottom: 12px; }
.legend .sw { display: inline-block; width: 11px; height: 11px; border-radius: 3px;
              margin-right: 6px; vertical-align: -1px; }
.bar-row { display: grid; grid-template-columns: 200px 1fr 92px; gap: 12px;
           align-items: center; padding: 6px 0; }
.bar-row .name { font-size: 13.5px; white-space: nowrap; overflow: hidden;
                 text-overflow: ellipsis; }
.bar-track { background: #efedea; border-radius: 5px; height: 16px; display: flex; }
.seg { height: 16px; min-width: 0; }
.seg:first-child { border-radius: 5px 0 0 5px; }
.seg:last-child { border-radius: 0 5px 5px 0; }
.seg:only-child { border-radius: 5px; }
.seg + .seg { margin-left: 2px; }
.bar-val { font-size: 12.5px; color: #52514e; text-align: right;
           font-variant-numeric: tabular-nums; }
.you-name { font-weight: 700; }
.badge { display: inline-block; font-size: 11px; font-weight: 650; padding: 1.5px 8px;
         border-radius: 999px; margin-left: 6px; vertical-align: 1px; white-space: nowrap; }
.b-you { background: #e3edfa; color: #17559c; }
.b-hot { background: #fdeade; color: #a53c12; }
.b-rising { background: #e2f4ec; color: #0c6b4a; }
.b-cooling { background: #efedea; color: #52514e; }
.b-ch { background: #f0eef7; color: #4a3aa7; margin-left: 0; margin-right: 6px; }
.b-comp { background: #f4e9ec; color: #8f2d4e; }
.opps { display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
        gap: 12px; margin-top: 12px; }
.opp { background: #fff; border: 1px solid #e2e0db; border-left: 4px solid #2a78d6;
       border-radius: 12px; padding: 16px 18px;
       box-shadow: 0 2px 8px rgba(16, 29, 51, .04); }
.opp .kw { font-size: 15.5px; font-weight: 700; margin: 2px 0 6px; }
.opp .why { font-size: 12.5px; color: #52514e; margin-top: 8px; }
.opp .act { font-size: 13px; margin-top: 8px; }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
th { text-align: left; color: #52514e; font-weight: 650; font-size: 11.5px;
     letter-spacing: .04em; text-transform: uppercase;
     padding: 6px 10px 6px 0; border-bottom: 1px solid #e2e0db; }
td { padding: 8px 10px 8px 0; border-bottom: 1px solid #f0efec; vertical-align: top; }
tr:last-child td { border-bottom: 0; }
td.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.scorebar { display: inline-block; height: 8px; border-radius: 4px;
            background: #2a78d6; vertical-align: 2px; margin-right: 8px; }
.tabs { display: flex; gap: 8px; margin: 14px 0 2px; }
.tab { font: inherit; font-size: 13.5px; font-weight: 650; color: #52514e;
       background: #fff; border: 1px solid #e2e0db; border-radius: 999px;
       padding: 7px 18px; cursor: pointer; }
.tab.on { background: #17559c; border-color: #17559c; color: #fff; }
.panel { display: none; } .panel.on { display: block; }
.cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(305px, 1fr));
        gap: 12px; }
.chhead { display: flex; align-items: baseline; gap: 8px; margin-bottom: 2px; }
.chhead h3 { font-size: 15px; }
.chhead .sub { color: #52514e; font-size: 12px; }
.card .chnote { color: #52514e; font-size: 12.5px; margin: 4px 0 10px; }
ol.gaps { padding-left: 20px; }
ol.gaps li { margin: 12px 0; }
ol.gaps .who { color: #52514e; font-size: 12.5px; }
.moment { display: grid; grid-template-columns: 118px 1fr; gap: 14px;
          padding: 9px 0; border-bottom: 1px solid #f0efec; font-size: 13.5px; }
.moment:last-child { border-bottom: 0; }
.moment .when { color: #52514e; font-variant-numeric: tabular-nums; }
footer { color: #52514e; font-size: 12px; margin-top: 48px; line-height: 1.6; }
@media (max-width: 640px) {
  .bar-row { grid-template-columns: 118px 1fr 70px; }
  .hero { padding-bottom: 96px; }
}
"""

JS = """
document.querySelectorAll('.tab').forEach(function (tab) {
  tab.addEventListener('click', function () {
    document.querySelectorAll('.tab').forEach(function (t) { t.classList.remove('on'); });
    document.querySelectorAll('.panel').forEach(function (p) { p.classList.remove('on'); });
    tab.classList.add('on');
    document.getElementById('panel-' + tab.dataset.h).classList.add('on');
  });
});
"""

BRAND_SEGS = ("#2a78d6", "#a7c8ef")     # AI answers / community — brand
OTHER_SEGS = ("#8a8984", "#d0cec8")     # AI answers / community — everyone else


def _esc(text) -> str:
    return html.escape(str(text))


def _split_bars(rows) -> str:
    """Ranked two-segment bars: (name, ai, community, is_you). The darker
    segment is AI-assistant answers, the lighter is community chatter; blue
    marks the brand, neutral everyone else — hue follows role, never rank."""
    top = max((ai + com for _n, ai, com, _y in rows), default=1.0) or 1.0
    out = [(
        '<div class="legend">'
        f'<span><span class="sw" style="background:{BRAND_SEGS[0]}"></span>AI-assistant answers</span>'
        f'<span><span class="sw" style="background:{BRAND_SEGS[1]}"></span>Community &amp; news</span>'
        "</div>")]
    for name, ai, com, is_you in rows:
        total = ai + com
        dark, light = BRAND_SEGS if is_you else OTHER_SEGS
        w_ai, w_com = 100 * ai / top, 100 * com / top
        you = ' <span class="badge b-you">you</span>' if is_you else ""
        cls = "name you-name" if is_you else "name"
        segs = ""
        if ai:
            segs += (f'<div class="seg" style="width:{w_ai:.1f}%;background:{dark}" '
                     f'title="{_esc(name)} — {ai:,.0f} AI-answer mentions"></div>')
        if com:
            segs += (f'<div class="seg" style="width:{w_com:.1f}%;background:{light}" '
                     f'title="{_esc(name)} — {com:,.0f} community mentions"></div>')
        out.append(
            f'<div class="bar-row"><div class="{cls}" title="{_esc(name)}">{_esc(name)}{you}</div>'
            f'<div class="bar-track">{segs}</div>'
            f'<div class="bar-val">{total:,.0f}</div></div>')
    return "".join(out)


def _bars(rows, *, unit: str = "") -> str:
    """Single-measure ranked bars: (name, value, is_you)."""
    top = max((v for _n, v, _y in rows), default=1.0) or 1.0
    out = []
    for name, value, is_you in rows:
        width = max(100.0 * value / top, 1.5)
        color = BRAND_SEGS[0] if is_you else OTHER_SEGS[1]
        you = ' <span class="badge b-you">you</span>' if is_you else ""
        cls = "name you-name" if is_you else "name"
        out.append(
            f'<div class="bar-row"><div class="{cls}" title="{_esc(name)}">{_esc(name)}{you}</div>'
            f'<div class="bar-track"><div class="seg" style="width:{width:.1f}%;'
            f'background:{color}" title="{_esc(name)} — {value:,.0f}{unit}"></div></div>'
            f'<div class="bar-val">{value:,.0f}{unit}</div></div>')
    return "".join(out)


def _momentum_badge(delta: float, velocity: float) -> str:
    if velocity >= 3.0:
        return '<span class="badge b-hot">act now</span>'
    if delta > 0.15:
        return '<span class="badge b-rising">rising</span>'
    if delta < -0.15:
        return '<span class="badge b-cooling">cooling</span>'
    return ""


def _focus_table(rows, is_competitor_term) -> str:
    if not rows:
        return '<p class="chnote">No signals yet — check back tomorrow.</p>'
    body = []
    for rank, (keyword, score, delta, vel) in enumerate(rows, 1):
        comp = (' <span class="badge b-comp" title="Competitor-branded territory: '
                'contest with comparison content, not a dedicated page">competitor'
                "</span>") if is_competitor_term(keyword) else ""
        body.append(
            f'<tr><td class="num">{rank}</td>'
            f"<td>{_esc(keyword)}{comp} {_momentum_badge(delta, vel)}</td>"
            f'<td class="num"><span class="scorebar" style="width:{max(score, 3) * 0.5:.0f}px"></span>'
            f"{score:.0f}</td></tr>")
    return ("<table><tr><th>#</th><th>Query / topic</th><th>Priority</th></tr>"
            + "".join(body) + "</table>")


def _top_opportunities(store: Store, cfg: dict, scores,
                       is_competitor_term, limit: int = 3) -> str:
    """The 'do these first' cards: best week-horizon picks across channels,
    each with the evidence that produced it and the channel-fit action.
    Competitor-branded terms never headline — 'create a page' for someone
    else's brand is not an opportunity."""
    best: dict[str, tuple[float, float, float, str]] = {}
    for channel in CHANNELS:
        for kw, score, delta, vel in scores("week", channel, limit=6):
            if is_competitor_term(kw):
                continue
            if kw not in best or score > best[kw][0]:
                best[kw] = (score, delta, vel, channel)
    picks = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)[:limit]
    cards = []
    for kw, (score, delta, vel, _ch) in picks:
        channels = sorted(channels_for(kw, cfg))
        chips = "".join(f'<span class="badge b-ch">{c.upper()}</span>' for c in channels)
        action = ACTIONS["geo"] if "geo" in channels else (
            ACTIONS["aeo"] if "aeo" in channels else ACTIONS["seo"])
        evidence = store.recent_discoveries(kw, days=30, limit=2)
        why = " · ".join(f"{_esc(ctx[:110])}" for _d, ctx, _s in evidence if ctx)
        why_html = f'<div class="why">Seen in: {why}</div>' if why else ""
        cards.append(
            f'<div class="opp">{chips}{_momentum_badge(delta, vel)}'
            f'<div class="kw">{_esc(kw)}</div>'
            f'<div class="act">{_esc(action)}</div>{why_html}</div>')
    return f'<div class="opps">{"".join(cards)}</div>'


def generate_dashboard(store: Store, cfg: dict, out_dir: Path,
                       extra_paths: list[Path] | None = None) -> Path:
    cur = store.conn.execute("SELECT MAX(date) FROM scores")
    score_date = (cur.fetchone() or [None])[0]
    is_competitor_term = competitor_matcher(cfg)
    excluded = excluded_keywords(cfg)

    def scores(horizon: str, channel: str, limit: int = 8):
        """latest_scores minus the team's exclude list — scores persist from
        the last data run, so a keyword vetoed in config must disappear from
        the page immediately, not after the next 40-minute pipeline run."""
        rows = store.latest_scores(score_date, horizon, channel, limit=limit + len(excluded))
        return [r for r in rows if r[0] not in excluded][:limit]
    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    split = store.entity_mention_split(days=7)
    visibility = store.entity_visibility(days=7)
    summary = citation_summary(store, cfg, days=30)
    gaps = citation_gaps(store, cfg, days=30, limit=8)
    events = upcoming_events(cfg, _date.today(), within_days=90)
    n_keywords = store.conn.execute(
        "SELECT COUNT(DISTINCT keyword) FROM scores WHERE date = ?",
        (score_date,)).fetchone()[0] if score_date else 0

    brand_sov = next((sov for _e, kind, _c, sov in visibility if kind == "brand"), None)
    own_citation = next((share for _d, _c, share, role in summary if role == "own"), None)
    leader = summary[0] if summary else None
    brand_rank = next((i + 1 for i, (_e, kind, _c, _s) in enumerate(visibility)
                       if kind == "brand"), None)

    parts: list[str] = []

    # --- hero + KPIs ------------------------------------------------------
    parts.append(
        '<div class="hero"><div class="wrap">'
        f"<h1>{_esc(cfg.get('project', 'TrendPulse'))}</h1>"
        f'<span class="tag">Search &amp; AI trend intelligence · {_esc(cfg.get("market", ""))}</span>'
        f'<span class="live">Updates daily · {_esc(generated)}</span>'
        "</div></div>")

    parts.append('<main class="wrap">')
    parts.append('<div class="kpis">')
    kpis = [
        (f"{brand_sov:.1f}<small>%</small>" if brand_sov is not None else "—",
         "share of voice when AI assistants &amp; communities discuss UAE banks (7 days)",
         (f'<div class="d flat">#{brand_rank} of the tracked banks</div>' if brand_rank else "")),
        (f"{own_citation:.1f}<small>%</small>" if own_citation is not None else "—",
         "of AI-engine citations for banking prompts go to adcb.com (30 days)",
         (f'<div class="d down">leader: {_esc(leader[0])} at {leader[2]:.1f}%</div>'
          if leader and leader[3] != "own" else
          '<div class="d up">you lead citations</div>' if leader else "")),
        (f"{n_keywords:,}", "queries &amp; topics tracked and re-scored every morning", ""),
        (f"{len(gaps)}", "AI questions currently answered with competitor sources — "
                         "each is a page to publish", ""),
    ]
    for value, label, delta_html in kpis:
        parts.append(f'<div class="kpi"><div class="v">{value}</div>'
                     f'<div class="l">{label}</div>{delta_html}</div>')
    parts.append("</div>")

    # --- top opportunities ------------------------------------------------
    if score_date:
        parts.append('<div class="eyebrow">Start here</div>')
        parts.append("<h2>This week&rsquo;s top opportunities</h2>")
        parts.append('<p class="note">The strongest signals right now, with the evidence '
                     "behind them and the play to run.</p>")
        parts.append(_top_opportunities(store, cfg, scores, is_competitor_term))

    # --- share of voice ---------------------------------------------------
    if split:
        parts.append('<div class="eyebrow">01 · The conversation</div>')
        parts.append("<h2>Who owns the banking conversation?</h2>")
        parts.append('<p class="note">Every time a bank is named in an AI-assistant answer '
                     "(ChatGPT, Gemini, Perplexity, AI Overviews) or in community chatter "
                     "(Reddit, news) over the last 7 days. Each sighting counts once. "
                     "Hover a bar segment for the split.</p>")
        rows = [(e, ai, com, kind == "brand") for e, kind, ai, com in split[:10]]
        parts.append(f'<div class="card">{_split_bars(rows)}</div>')

    # --- citations --------------------------------------------------------
    if summary:
        parts.append('<div class="eyebrow">02 · Inside AI answers</div>')
        parts.append("<h2>Who do AI engines cite for banking questions?</h2>")
        parts.append('<p class="note">The websites AI assistants link as sources when '
                     "answering banking &amp; finance prompts (last 30 days). More citations "
                     "&rarr; more presence inside the answers customers actually read.</p>")
        own = {d for d, _c, _s, r in summary if r == "own"}
        rows = [(d, c, d in own) for d, c, _share, _r in summary[:10]]
        parts.append(f'<div class="card">{_bars(rows)}</div>')

    # --- citation gaps ----------------------------------------------------
    if gaps:
        parts.append('<div class="eyebrow">03 · Content backlog</div>')
        parts.append("<h2>Publish these next — the citation gaps</h2>")
        parts.append('<p class="note">Real questions people asked AI assistants where the '
                     "answer cited other banks but never adcb.com. A clear, citable page "
                     "for each is the fastest way into those answers.</p>")
        items = []
        for gap in gaps:
            items.append(f"<li><strong>{_esc(gap['prompt'])}</strong><br>"
                         f'<span class="who">currently cited: '
                         f"{_esc(', '.join(gap['domains'][:4]))} &middot; asked on "
                         f"{_esc(', '.join(gap['models'][:4]))}</span></li>")
        parts.append(f'<div class="card"><ol class="gaps">{"".join(items)}</ol></div>')

    # --- focus queries, tabbed by horizon --------------------------------
    if score_date:
        parts.append('<div class="eyebrow">04 · Focus queries</div>')
        parts.append("<h2>What to optimize for</h2>")
        parts.append('<p class="note">Ranked by predicted growth in attention across all '
                     "sources — including the bank&rsquo;s own Search Console history. "
                     "Priority is a percentile: 100 = strongest signal today.</p>")
        horizons = list(cfg["model"]["horizons"])
        parts.append('<div class="tabs">')
        for i, horizon in enumerate(horizons):
            on = " on" if i == 0 else ""
            parts.append(f'<button class="tab{on}" data-h="{horizon}" type="button">'
                         f"{HORIZON_TITLES.get(horizon, horizon)}</button>")
        parts.append("</div>")
        for i, horizon in enumerate(horizons):
            on = " on" if i == 0 else ""
            parts.append(f'<div class="panel{on}" id="panel-{horizon}"><div class="cols">')
            for channel in CHANNELS:
                abbr, subtitle, blurb = CHANNEL_META[channel]
                rows = scores(horizon, channel, limit=8)
                parts.append(
                    f'<div class="card"><div class="chhead"><h3>{abbr}</h3>'
                    f'<span class="sub">{subtitle}</span></div>'
                    f'<p class="chnote">{blurb}</p>'
                    f'{_focus_table(rows, is_competitor_term)}</div>')
            parts.append("</div></div>")

    # --- regional moments -------------------------------------------------
    if events:
        parts.append('<div class="eyebrow">05 · Plan ahead</div>')
        parts.append("<h2>Upcoming regional moments</h2>")
        parts.append('<p class="note">Content must rank <em>before</em> the moment, not '
                     "during it. Dates marked ~ follow the Hijri calendar — verify before "
                     "publishing.</p>")
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
                 "NASA EONET, TryProfound (AI-assistant answers), Google Search Console + "
                 "GA4 imports. Scores are directional decision-support — validate big bets "
                 "against Search Console before committing serious resources. Analyst "
                 "detail: reports/latest.md and per-channel CSVs in the repository.</footer>")
    parts.append("</main>")

    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{_esc(cfg.get('project', 'TrendPulse'))} — trend dashboard</title>"
            f"<style>{CSS}</style></head><body>"
            + "".join(parts)
            + f"<script>{JS}</script></body></html>")

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "dashboard.html"
    path.write_text(page, encoding="utf-8")
    for extra in extra_paths or []:
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text(page, encoding="utf-8")
    log.info("dashboard written to %s", path)
    return path
