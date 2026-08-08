import json

from trendpulse.collectors.profound import ProfoundCollector

CFG = {"profound": {"category_name": "banking and finance", "asset": "adcb.com"}}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _collector(monkeypatch):
    collector = ProfoundCollector(CFG)
    monkeypatch.setenv("PROFOUND_API_KEY", "test-key")
    collector.api_key = "test-key"

    def fake_get(url, timeout=None, headers=None):
        assert headers["X-API-Key"] == "test-key"
        if url.endswith("/v1/org/categories"):
            return FakeResponse({"data": [{"id": "cat-1", "name": "Banking & Finance"}]})
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(url, json=None, timeout=None, headers=None):  # noqa: A002
        body = json
        assert headers["X-API-Key"] == "test-key"
        if url.endswith("/v2/reports/visibility"):
            assert body["category_id"] == "cat-1"  # auto-discovered
            return FakeResponse({"data": [
                {"asset": {"name": "adcb.com"}, "share_of_voice": 14.5,
                 "visibility_score": 61.0},
                {"asset": {"name": "Emirates NBD"}, "share_of_voice": 32.0,
                 "visibility_score": 80.0},
            ]})
        if url.endswith("/v2/prompts/answers"):
            return FakeResponse({"data": [
                {"prompt": "What is the best bank in the UAE for savings?",
                 "model": "ChatGPT", "topic": "Savings",
                 "mentions": ["ADCB", "Emirates NBD"],
                 "citations": ["https://www.adcb.com/en/savings/"]},
            ]})
        raise AssertionError(f"unexpected POST {url}")

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)
    return collector


def test_profound_end_to_end(monkeypatch):
    collector = _collector(monkeypatch)
    obs, discs, mentions = collector.safe_fetch([])

    metrics = {(o.keyword, o.metric): o.value for o in obs}
    assert metrics[("adcbcom", "ai_share_of_voice")] == 14.5
    assert metrics[("emirates nbd", "ai_visibility")] == 80.0

    kinds = {(m.entity, m.kind) for m in mentions}
    assert ("ADCB", "brand") in kinds
    assert ("Emirates NBD", "competitor") in kinds

    prompts = [d for d in discs if d.keyword.startswith("what is")]
    assert prompts and "ChatGPT" in prompts[0].context
    # citations are captured as structured rows, not keyword discoveries
    assert any(c.domain == "adcb.com" and "savings" in c.url
               for c in collector.citations)
    assert collector.citations[0].prompt.startswith("What is the best bank")


def test_profound_survives_bare_list_responses(monkeypatch):
    """Regression: the live API can answer with a bare JSON list instead of an
    {info, data} envelope. The 2026-08-08 production run crashed on exactly
    this ("'list' object has no attribute 'get'"), and safe_fetch swallowed
    it — a whole day of AI share-of-voice silently became zero rows."""
    collector = ProfoundCollector(CFG)
    collector.api_key = "test-key"

    def fake_get(url, timeout=None, headers=None):
        # bare list, no envelope — the shape that crashed production
        return FakeResponse([{"id": "cat-1", "name": "Banking & Finance"}])

    def fake_post(url, json=None, timeout=None, headers=None):  # noqa: A002
        if url.endswith("/v2/reports/visibility"):
            return FakeResponse([
                {"asset": {"name": "adcb.com"}, "share_of_voice": 14.5,
                 "visibility_score": 61.0},
                "unexpected-string-row",  # junk rows must be skipped, not fatal
            ])
        return FakeResponse([
            {"prompt": "Which UAE bank has the best mortgage?",
             "model": "Perplexity", "mentions": ["FAB"],
             "citations": ["https://www.fab.ae/mortgages"]},
        ])

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)

    obs, discs, mentions = collector.safe_fetch([])
    assert {(o.keyword, o.metric) for o in obs} == {
        ("adcbcom", "ai_share_of_voice"), ("adcbcom", "ai_visibility")}
    assert any(d.keyword.startswith("which uae bank") for d in discs)
    assert ("FAB", "competitor") in {(m.entity, m.kind) for m in mentions}
    assert collector.citations and collector.citations[0].domain == "fab.ae"


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
