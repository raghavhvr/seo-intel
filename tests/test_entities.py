from datetime import date, timedelta

# Relative dates: the read paths under test use rolling 7-day windows, so
# hardcoded dates turn into time bombs the week after they are written.
def _d(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()

from trendpulse.entities import scan_discoveries
from trendpulse.storage import Store
from trendpulse.types import Discovery

CFG = {"entities": {"brand": ["ADCB"], "competitors": ["Emirates NBD", "FAB", "Wio"]}}


def test_scan_discoveries_finds_mentions(tmp_path):
    store = Store(tmp_path / "t.db")
    discs = [
        Discovery(date=_d(2), keyword="adcb vs emirates nbd savings account",
                  source="reddit", context="r/dubai thread", score=12.0),
        Discovery(date=_d(2), keyword="first abu dhabi bank launches new app",
                  source="google_news", context="headline", score=5.0),  # FAB alias
        Discovery(date=_d(2), keyword="unrelated weather news",
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
        date=_d(2), entity="ADCB", kind="brand", source="google_trends",
        context="rising related query for 'adcb' in KW", value=282400.0)])
    discs = [
        Discovery(date=_d(1), keyword="emirates nbd rates",
                  source="google_trends", context="rising", score=161100.0),
        Discovery(date=_d(1), keyword="adcb credit card offer",
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
        EntityMention(date=_d(1), entity=e, kind="competitor", source=s,
                      context=f"ctx {i}") for i, (e, s) in enumerate(rows)])
    split = store.entity_mention_split(days=7)
    assert [(e, ai, com) for e, _k, ai, com in split] == [
        ("ADCB", 3.0, 2.0), ("Emirates NBD", 4.0, 0.0), ("ADNOC", 0.0, 1.0)]
    store.close()


def test_competitor_matcher_flags_branded_territory():
    from trendpulse.entities import competitor_matcher

    is_comp = competitor_matcher({"entities": {"competitors":
                                               ["Emirates NBD", "Mashreq", "FAB", "Wio"]}})
    assert is_comp("mashreq neo account opening")
    assert is_comp("emirates nbd balance check")     # multi-word competitor
    assert is_comp("enbd credit card")               # built-in alias
    assert not is_comp("credit card uae")
    assert not is_comp("fabulous savings tips")      # word boundary holds
    assert not competitor_matcher({})("mashreq neo")  # no config -> no flags


def test_word_boundaries_prevent_false_positives(tmp_path):
    store = Store(tmp_path / "t.db")
    discs = [Discovery(date=_d(2), keyword="fabulous credit card hacks",
                       source="reddit", context="", score=1.0)]
    assert scan_discoveries(CFG, store, discs) == 0  # "fabulous" must not match "FAB"
    store.close()


def test_canonicalizer_merges_aliases():
    from trendpulse.entities import canonicalizer

    canon = canonicalizer({"entities": {
        "brand": ["ADCB", "Abu Dhabi Commercial Bank", "بنك أبوظبي التجاري"],
        "competitors": ["Emirates NBD", "FAB", "ADIB", "Sarwa"]}})
    # brand family -> one display name
    assert canon("ADCB") == ("ADCB", "brand")
    assert canon("Abu Dhabi Commercial Bank") == ("ADCB", "brand")
    assert canon("بنك أبوظبي التجاري") == ("ADCB", "brand")
    # FAB family, including forms only Profound emits
    assert canon("First Abu Dhabi Bank") == ("FAB", "competitor")
    assert canon("FAB Bank") == ("FAB", "competitor")
    assert canon("بنك أبوظبي الأول") == ("FAB", "competitor")
    # adjacent Abu Dhabi banks must NOT collapse into each other
    assert canon("Abu Dhabi Islamic Bank") == ("ADIB", "competitor")
    assert canon("ENBD") == ("Emirates NBD", "competitor")
    # unknown names pass through so auto-discovered entities still show
    assert canon("Ruya Bank")[0] == "Ruya Bank"
    assert canon("Sarwa") == ("Sarwa", "competitor")


def test_one_sighting_one_mention_after_canonicalization(tmp_path):
    """'First Abu Dhabi Bank' used to match both the 'FAB' and the
    'First Abu Dhabi Bank' config entries -> two rows for one sighting."""
    store = Store(tmp_path / "t.db")
    cfg = {"entities": {"brand": ["ADCB", "Abu Dhabi Commercial Bank"],
                        "competitors": ["Emirates NBD", "FAB"]}}
    n = scan_discoveries(cfg, store, [Discovery(
        date=_d(0), keyword="first abu dhabi bank launches app",
        source="news", context="x", score=1.0)])
    assert n == 1
    n2 = scan_discoveries(cfg, store, [Discovery(
        date=_d(0), keyword="abu dhabi commercial bank results",
        source="news", context="y", score=1.0)])
    assert n2 == 1
    split = store.entity_mention_split(days=7)
    assert {(e, k) for e, k, _a, _c in split} == {("FAB", "competitor"), ("ADCB", "brand")}
    store.close()


def test_rolled_up_split_merges_history(tmp_path):
    """Historical rows written under surface forms merge at read time."""
    from trendpulse.entities import rolled_up_split
    from trendpulse.types import EntityMention

    store = Store(tmp_path / "t.db")
    rows = [("ADCB", "brand", "profound:ChatGPT"),
            ("Abu Dhabi Commercial Bank", "brand", "reddit"),
            ("بنك أبوظبي التجاري", "brand", "profound:Gemini"),
            ("FAB", "competitor", "profound:ChatGPT"),
            ("First Abu Dhabi Bank", "competitor", "google_news"),
            ("FAB Bank", "competitor", "profound:Perplexity")]
    store.upsert_entity_mentions([EntityMention(
        date=_d(0), entity=e, kind=k, source=s, context=f"c{i}")
        for i, (e, k, s) in enumerate(rows)])
    cfg = {"entities": {"brand": ["ADCB", "Abu Dhabi Commercial Bank"],
                        "competitors": ["FAB"]}}
    split = rolled_up_split(store, cfg, days=7)
    assert [(e, k, ai + com) for e, k, ai, com in split] == [
        ("ADCB", "brand", 3.0), ("FAB", "competitor", 3.0)]
    store.close()
