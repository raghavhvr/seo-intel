from trendpulse.entities import scan_discoveries
from trendpulse.storage import Store
from trendpulse.types import Discovery

CFG = {"entities": {"brand": ["ADCB"], "competitors": ["Emirates NBD", "FAB", "Wio"]}}


def test_scan_discoveries_finds_mentions(tmp_path):
    store = Store(tmp_path / "t.db")
    discs = [
        Discovery(date="2026-08-07", keyword="adcb vs emirates nbd savings account",
                  source="reddit", context="r/dubai thread", score=12.0),
        Discovery(date="2026-08-07", keyword="first abu dhabi bank launches new app",
                  source="google_news", context="headline", score=5.0),  # FAB alias
        Discovery(date="2026-08-07", keyword="unrelated weather news",
                  source="google_news", context="", score=1.0),
    ]
    written = scan_discoveries(CFG, store, discs)
    assert written == 3  # ADCB + Emirates NBD in #1, FAB (aliased) in #2

    visibility = store.entity_visibility(days=7)
    by_entity = {e: (k, sov) for e, _k, _c, sov in visibility for k in [_k]}
    assert by_entity["ADCB"][0] == "brand"
    assert by_entity["FAB"][0] == "competitor"
    assert sum(sov for _e, _k, _c, sov in visibility) == 100.0

    contexts = store.entity_contexts("ADCB")
    assert contexts and "r/dubai" in contexts[0][2]
    store.close()


def test_mentions_count_once_regardless_of_discovery_score(tmp_path):
    """A pytrends breakout discovery carries a percent-growth score (282400 in
    production); summed as a mention value it once gave ADCB 97% SOV off two
    rows. Every sighting counts exactly once, and stored history collected
    under the old weighting is clamped on the next scan."""
    from trendpulse.types import EntityMention

    store = Store(tmp_path / "t.db")
    # history written by the old code: score used as value
    store.upsert_entity_mentions([EntityMention(
        date="2026-08-07", entity="ADCB", kind="brand", source="google_trends",
        context="rising related query for 'adcb' in KW", value=282400.0)])
    discs = [
        Discovery(date="2026-08-08", keyword="emirates nbd rates",
                  source="google_trends", context="rising", score=161100.0),
        Discovery(date="2026-08-08", keyword="adcb credit card offer",
                  source="reddit", context="thread", score=3.0),
    ]
    scan_discoveries(CFG, store, discs)
    import pytest

    visibility = {e: (mentions, sov) for e, _k, mentions, sov in store.entity_visibility()}
    assert visibility["ADCB"] == (2.0, pytest.approx(200 / 3))   # clamped history + new row
    assert visibility["Emirates NBD"] == (1.0, pytest.approx(100 / 3))  # breakout score ignored
    store.close()


def test_mention_split_is_ranked_by_total(tmp_path):
    """AI vs community split, ordered by total mentions — a plain 'ORDER BY
    3 + 4' silently becomes the constant 7 in SQLite (no ordering), which put
    1-mention entities above Emirates NBD on the dashboard."""
    from trendpulse.types import EntityMention

    store = Store(tmp_path / "t.db")
    rows = ([("ADCB", "profound:ChatGPT")] * 3 + [("ADCB", "reddit")] * 2
            + [("Emirates NBD", "profound:Gemini")] * 4
            + [("ADNOC", "google_news")])
    store.upsert_entity_mentions([
        EntityMention(date="2026-08-08", entity=e, kind="competitor", source=s,
                      context=f"ctx {i}") for i, (e, s) in enumerate(rows)])
    split = store.entity_mention_split(days=7)
    assert [(e, ai, com) for e, _k, ai, com in split] == [
        ("ADCB", 3.0, 2.0), ("Emirates NBD", 4.0, 0.0), ("ADNOC", 0.0, 1.0)]
    store.close()


def test_word_boundaries_prevent_false_positives(tmp_path):
    store = Store(tmp_path / "t.db")
    discs = [Discovery(date="2026-08-07", keyword="fabulous credit card hacks",
                       source="reddit", context="", score=1.0)]
    assert scan_discoveries(CFG, store, discs) == 0  # "fabulous" must not match "FAB"
    store.close()
