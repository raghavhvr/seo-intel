from datetime import date, timedelta

# Relative dates: the read paths under test use rolling 7-day windows, so
# hardcoded dates turn into time bombs the week after they are written.
def _d(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()

from trendpulse.gaps import citation_gaps, citation_summary, own_domains
from trendpulse.notify import build_alert_text, send_alerts
from trendpulse.storage import Store
from trendpulse.types import Citation

CFG = {
    "project": "ADCB",
    "brand_domains": ["adcb.com"],
    "competitor_domains": ["emiratesnbd.com", "wio.io"],
    "profound": {"asset": "adcb.com"},
    "alerts": {"enabled": True, "breakout_z": 3.0, "max_items": 5,
               "report_url": "https://example.com/report"},
}


def _store_with_citations(tmp_path):
    store = Store(tmp_path / "t.db")
    store.upsert_citations([
        Citation(date=_d(2), url="https://www.adcb.com/en/savings/",
                 domain="adcb.com", prompt="best savings account uae", model="ChatGPT"),
        Citation(date=_d(2), url="https://www.emiratesnbd.com/en/savings/",
                 domain="emiratesnbd.com", prompt="best savings account uae", model="ChatGPT"),
        Citation(date=_d(2), url="https://wio.io/personal",
                 domain="wio.io", prompt="how to open a bank account in uae", model="Gemini"),
        Citation(date=_d(3), url="https://wio.io/personal",
                 domain="wio.io", prompt="how to open a bank account in uae", model="ChatGPT"),
        Citation(date=_d(2), url="https://www.emiratesnbd.com/en/cards/",
                 domain="emiratesnbd.com", prompt="best credit card uae", model="Perplexity"),
    ])
    return store


def test_own_domains_merges_asset(tmp_path):
    assert own_domains(CFG) == {"adcb.com"}
    assert own_domains({"brand_domains": [], "profound": {"asset": "www.adcb.com"}}) == {"adcb.com"}


def test_citation_summary_roles(tmp_path):
    store = _store_with_citations(tmp_path)
    summary = {d: (c, s, r) for d, c, s, r in citation_summary(store, CFG, days=30)}
    assert summary["adcb.com"][2] == "own"
    assert summary["emiratesnbd.com"][2] == "competitor"
    assert summary["wio.io"][2] == "competitor"
    assert abs(sum(v[1] for v in summary.values()) - 100.0) < 0.01
    store.close()


def test_citation_gaps_exclude_prompts_we_win(tmp_path):
    store = _store_with_citations(tmp_path)
    gaps = citation_gaps(store, CFG, days=30)
    prompts = [g["prompt"] for g in gaps]
    # "best savings account uae" cites adcb.com — not a gap
    assert "best savings account uae" not in prompts
    # ranked by citation count: the twice-cited account-opening prompt first
    assert prompts[0] == "how to open a bank account in uae"
    assert "best credit card uae" in prompts
    assert all(not g["cites_us"] for g in gaps)
    store.close()


def test_alert_text_contains_breakouts_and_sov(tmp_path):
    store = _store_with_citations(tmp_path)
    store.save_score(_d(2), "bnpl uae", "week", "seo", 97.0, 2.1, 4.2)
    store.save_score(_d(2), "crm software", "week", "seo", 40.0, 0.1, 1.0)
    store.upsert_entity_mentions([])
    from trendpulse.types import EntityMention
    store.upsert_entity_mentions([
        EntityMention(date=_d(2), entity="ADCB", kind="brand",
                      source="profound", value=3.0),
        EntityMention(date=_d(2), entity="Emirates NBD", kind="competitor",
                      source="profound", value=7.0),
    ])
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    store.save_score(today, "bnpl uae", "week", "seo", 97.0, 2.1, 4.2)

    text = build_alert_text(CFG, store, "reports/latest.md")
    assert "bnpl uae" in text and "breakout" in text.lower()
    assert "crm software" not in text.split("breakout")[1].split("Top focus")[0]
    assert "AI share of voice" in text and "ADCB" in text
    assert "https://example.com/report" in text
    store.close()


def test_send_alerts_no_webhooks_is_quiet(tmp_path, monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("TEAMS_WEBHOOK_URL", raising=False)
    store = _store_with_citations(tmp_path)
    assert send_alerts(CFG, store) is False
    store.close()


def test_send_alerts_posts_to_slack(tmp_path, monkeypatch):
    sent = []

    class FakeResp:
        def raise_for_status(self):
            pass

    def fake_post(url, json=None, timeout=None):
        sent.append((url, json))
        return FakeResp()

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    monkeypatch.setattr("requests.post", fake_post)
    store = _store_with_citations(tmp_path)
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    store.save_score(today, "bnpl uae", "week", "seo", 97.0, 2.1, 4.2)
    assert send_alerts(CFG, store) is True
    assert sent and "bnpl uae" in sent[0][1]["text"]
    store.close()
