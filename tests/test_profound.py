from trendpulse.collectors.profound import ProfoundCollector

CFG = {"profound": {"category_name": "banking and finance", "asset": "adcb.com"}}

# v1 report rows carry parallel `dimensions`/`metrics` arrays whose order is
# ALPHABETICAL by field name, NOT request order (verified live 2026-08-05).
# dimensions ["asset_name", "date"] -> [name, date]
# metrics ["share_of_voice", "visibility_score"] -> [sov, vis]
# The fixture values are deliberately asymmetric so a positional transposition
# (sov read as visibility) fails the assertions.
VISIBILITY_PAGE = {"info": {"total_rows": 2}, "data": [
    {"dimensions": ["adcb.com", "2026-08-07"], "metrics": [14.5, 61.0]},
    {"dimensions": ["Emirates NBD", "2026-08-07"], "metrics": [32.0, 80.0]},
]}

ANSWER_PAGE_1 = {"info": {"next_cursor": "cursor-2"}, "data": [
    {"prompt": "What is the best bank in the UAE for savings?",
     "model": {"id": "m1", "name": "ChatGPT"},      # model is an object in v2
     "topic": {"id": "t1", "name": "Savings"},
     "mentions": ["ADCB", "Emirates NBD"],
     "citations": ["https://www.adcb.com/en/savings/"]},
]}
ANSWER_PAGE_2 = {"info": {"next_cursor": None}, "data": [
    {"prompt": "Which UAE bank has the best mortgage?",
     "model": "Perplexity",                          # tolerate plain strings too
     "mentions": ["FAB"],
     "citations": ["https://www.fab.ae/mortgages"]},
]}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _collector(monkeypatch, visibility_payload=VISIBILITY_PAGE):
    collector = ProfoundCollector(CFG)
    collector.api_key = "test-key"
    calls = {"answers": []}

    def fake_get(url, timeout=None, headers=None):
        assert headers["X-API-Key"] == "test-key"
        if url.endswith("/v1/org/categories"):
            # bare list, no envelope — the shape that crashed prod on 08-08
            return FakeResponse([{"id": "cat-1", "name": "Banking - Finance"}])
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(url, json=None, timeout=None, headers=None):  # noqa: A002
        body = json
        assert headers["X-API-Key"] == "test-key"
        if url.endswith("/v1/reports/visibility"):
            assert body["category_id"] == "cat-1"  # auto-discovered
            assert body["dimensions"] == ["asset_name", "date"]
            assert "group_by" not in body  # v2-ism; rejected with HTTP 422
            return FakeResponse(visibility_payload)
        if url.endswith("/v2/prompts/answers"):
            assert body["limit"] == 200  # API default of 10 discards the day
            calls["answers"].append(body.get("cursor"))
            return FakeResponse(ANSWER_PAGE_2 if body.get("cursor") else ANSWER_PAGE_1)
        raise AssertionError(f"unexpected POST {url}")

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)
    return collector, calls


def test_profound_end_to_end(monkeypatch):
    collector, calls = _collector(monkeypatch)
    obs, discs, mentions = collector.safe_fetch([])

    # dated by the row's own date dimension, mapped alphabetically — a
    # positional read would report visibility 14.5 and share of voice 61.0
    metrics = {(o.keyword, o.metric): (o.date, o.value) for o in obs}
    assert metrics[("adcbcom", "ai_share_of_voice")] == ("2026-08-07", 14.5)
    assert metrics[("adcbcom", "ai_visibility")] == ("2026-08-07", 61.0)
    assert metrics[("emirates nbd", "ai_visibility")][1] == 80.0

    kinds = {(m.entity, m.kind) for m in mentions}
    assert ("adcb.com", "brand") in kinds
    assert ("Emirates NBD", "competitor") in kinds
    assert ("ADCB", "brand") in kinds  # from answer mentions

    # both cursor pages consumed; model objects render as their names
    assert calls["answers"] == [None, "cursor-2"]
    by_kw = {d.keyword: d for d in discs}
    assert "ChatGPT" in by_kw["what is the best bank in the uae for savings"].context
    assert "Perplexity" in by_kw["which uae bank has the best mortgage"].context

    domains = {c.domain for c in collector.citations}
    assert domains == {"adcb.com", "fab.ae"}


def test_profound_survives_junk_rows_and_bare_lists(monkeypatch):
    """Envelope-less lists and non-dict rows must degrade row-by-row, never
    kill the collector (the 08-08 failure mode)."""
    junk = [  # bare list instead of {info, data}
        {"dimensions": ["adcb.com", "2026-08-07"], "metrics": [14.5, 61.0]},
        "unexpected-string-row",
    ]
    collector, _ = _collector(monkeypatch, visibility_payload=junk)
    obs, discs, mentions = collector.safe_fetch([])
    assert {(o.keyword, o.metric) for o in obs} == {
        ("adcbcom", "ai_share_of_voice"), ("adcbcom", "ai_visibility")}
    assert discs and mentions


def test_profound_handles_unrecognizable_payloads(monkeypatch):
    """A null or scalar payload yields empty results, never an exception."""
    collector = ProfoundCollector(CFG)
    collector.api_key = "test-key"
    monkeypatch.setattr("requests.get",
                        lambda url, timeout=None, headers=None: FakeResponse(None))
    assert collector.safe_fetch([]) == ([], [], [])


def test_profound_skips_without_key(monkeypatch):
    monkeypatch.delenv("PROFOUND_API_KEY", raising=False)
    collector = ProfoundCollector(CFG)
    assert not collector.available()
    assert collector.safe_fetch([]) == ([], [], [])
