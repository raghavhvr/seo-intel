from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import requests

from trendpulse.storage import Store

log = logging.getLogger(__name__)


def build_alert_text(cfg: dict, store: Store, report_path: str) -> str | None:
    """Morning briefing: breakouts to act on now, top weekly picks, brand SOV.
    Returns None when there is nothing worth sending."""
    alerts_cfg = cfg.get("alerts", {})
    threshold = float(alerts_cfg.get("breakout_z", 3.0))
    max_items = int(alerts_cfg.get("max_items", 8))
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    cur = store.conn.execute(
        "SELECT DISTINCT keyword, velocity_z, trend_score FROM scores"
        " WHERE date = ? AND horizon = 'week' AND velocity_z >= ?"
        " ORDER BY velocity_z DESC LIMIT ?",
        (date, threshold, max_items),
    )
    breakouts = cur.fetchall()
    top = store.latest_scores(date, "week", "seo", limit=3)

    if not breakouts and not top:
        return None

    project = cfg.get("project", "TrendPulse")
    lines = [f"*TrendPulse — {project} — {date}*"]
    if breakouts:
        lines.append(f"\n:rotating_light: *{len(breakouts)} breakout"
                     f"{'s' if len(breakouts) != 1 else ''} to act on this week:*")
        for kw, z, score in breakouts:
            lines.append(f"• {kw} (velocity z={z:+.1f}, score {score:.0f})")
    if top:
        lines.append("\n*Top focus queries this week:*")
        for kw, score, delta, _z in top:
            direction = "rising" if delta > 0.15 else ("cooling" if delta < -0.15 else "steady")
            lines.append(f"• {kw} — {direction} ({delta:+.2f}), score {score:.0f}")

    from trendpulse.entities import rolled_up_visibility
    visibility = rolled_up_visibility(store, cfg, days=7)
    brand = next((row for row in visibility if row[1] == "brand"), None)
    if brand:
        lines.append(f"\nAI share of voice (7d): *{brand[0]}* {brand[3]:.1f}%")

    url = alerts_cfg.get("report_url", "")
    if url:
        lines.append(f"\nFull report: {url}")
    elif report_path:
        lines.append(f"\nFull report: {report_path}")
    return "\n".join(lines)


def _post(url: str, payload: dict) -> bool:
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        log.warning("[notify] webhook failed: %s", exc)
        return False


def send_alerts(cfg: dict, store: Store, report_path: str = "") -> bool:
    """Send the briefing to Slack and/or Teams when webhooks are configured.
    Missing webhooks or network failures never fail the daily run."""
    if not cfg.get("alerts", {}).get("enabled", True):
        return False
    text = build_alert_text(cfg, store, report_path)
    if not text:
        log.info("[notify] nothing worth alerting today")
        return False

    sent = False
    slack = os.environ.get(cfg.get("alerts", {}).get("slack_webhook_env", "SLACK_WEBHOOK_URL"), "")
    teams = os.environ.get(cfg.get("alerts", {}).get("teams_webhook_env", "TEAMS_WEBHOOK_URL"), "")
    if slack:
        sent |= _post(slack, {"text": text})
        log.info("[notify] slack: %s", "sent" if sent else "failed")
    if teams:
        ok = _post(teams, {"title": "TrendPulse daily briefing", "text": text})
        sent |= ok
        log.info("[notify] teams: %s", "sent" if ok else "failed")
    if not slack and not teams:
        log.info("[notify] no webhooks configured (SLACK_WEBHOOK_URL / TEAMS_WEBHOOK_URL)")
    return sent
