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


def test_word_boundaries_prevent_false_positives(tmp_path):
    store = Store(tmp_path / "t.db")
    discs = [Discovery(date="2026-08-07", keyword="fabulous credit card hacks",
                       source="reddit", context="", score=1.0)]
    assert scan_discoveries(CFG, store, discs) == 0  # "fabulous" must not match "FAB"
    store.close()
