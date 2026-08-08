"""Signal-quality guards: the keyword->article gate, per-source blending,
and the un-geo-filtered news feed."""
from __future__ import annotations

import pandas as pd

from trendpulse.features import blended_attention, source_family
from trendpulse.wikimatch import best_match, configured_article, content_tokens, matches

# Real top hits from the Wikipedia search API for the shipped UAE banking
# seeds — every one of these was silently accepted before the gate existed.
REAL_MISMATCHES = [
    ("credit card uae", "RuPay"),
    ("personal loan uae", "United Arab Emirates"),
    ("best savings account uae", "Revolut"),
    ("how to check credit score in uae", "The Diplomat (2025 film)"),
    ("bnpl uae", "Uzum"),
    ("remittance uae to india", "UAE Exchange"),
    ("الدرهم الرقمي", "درهم مغربي"),          # digital dirham -> Moroccan dirham
    ("حساب توفير الإمارات", "بريد الإمارات"),   # savings account -> Emirates Post
    ("التمويل العقاري الإمارات", "بيت التمويل الكويتي"),  # mortgage -> Kuwait Finance House
]


def test_off_topic_articles_are_rejected():
    for keyword, top_hit in REAL_MISMATCHES:
        assert not matches(keyword, top_hit), f"{keyword!r} wrongly matched {top_hit!r}"


def test_genuine_articles_are_accepted():
    assert matches("credit card uae", "Credit card")
    assert matches("best credit card uae", "Credit card")
    assert matches("islamic banking uae", "Islamic banking and finance")
    assert matches("neobank uae", "Neobank")
    assert matches("adcb", "ADCB")


def test_a_one_word_subject_needs_an_exact_article():
    # 'best bank in the UAE' reduces to {بنك}; every named bank's article
    # covers that token, so coverage alone accepted a Lebanese bank.
    assert not matches("أفضل بنك في الإمارات", "بنك عوده")
    assert matches("أفضل بنك في الإمارات", "بنك")
    # Two-token subjects keep the looser rule, so real articles still pass.
    assert matches("islamic banking uae", "Islamic banking and finance")


def test_market_and_intent_words_are_not_required_of_the_title():
    assert content_tokens("best credit card uae online") == {"credit", "card"}
    assert content_tokens("قرض شخصي الإمارات") == {"قرض", "شخصي"}
    # A keyword that is nothing but market/intent words has no subject at all.
    assert content_tokens("best uae") == set()
    assert not matches("best uae", "United Arab Emirates")


def test_arabic_definite_article_does_not_create_false_matches():
    # الدرهم / درهم must compare equal, so this is a real 1-of-2 token overlap
    # rather than a spelling artefact — and partial overlap is still a reject.
    assert "درهم" in content_tokens("الدرهم الرقمي")
    assert not matches("الدرهم الرقمي", "درهم إماراتي")
    assert matches("الدرهم الرقمي", "الدرهم الرقمي الإماراتي")


def test_best_match_prefers_the_narrowest_passing_title():
    assert best_match("credit card uae", ["Credit card fraud", "Credit card"]) == "Credit card"
    assert best_match("car loan uae", ["RuPay", "United Arab Emirates"]) is None


def test_curated_overrides_bypass_the_gate():
    cfg = {"wikipedia": {"articles": {
        "digital dirham": "Digital currency",
        "ar": {"الدرهم الرقمي": "عملة رقمية"},
    }}}
    assert configured_article(cfg, "digital dirham", "en") == "Digital currency"
    assert configured_article(cfg, "الدرهم الرقمي", "ar") == "عملة رقمية"
    assert configured_article(cfg, "car loan uae", "en") is None
    assert configured_article({}, "digital dirham", "en") is None


def _index(days: int = 40) -> pd.DatetimeIndex:
    return pd.to_datetime(pd.date_range("2026-01-01", periods=days, freq="D"))


def _ramp(index: pd.DatetimeIndex) -> dict[str, float]:
    return {str(d.date()): float(i) for i, d in enumerate(index)}


def _flat(index: pd.DatetimeIndex) -> dict[str, float]:
    return {str(d.date()): 1.0 for d in index}


def test_duplicate_series_from_one_source_do_not_inflate_breadth():
    """Google News used to emit the same feed once per country. Three copies of
    one source must still count as one source of confirmation."""
    index = _index()
    one_region = {("google_news", "articles_7d", "AE", "en"): _ramp(index)}
    three_regions = {
        ("google_news", "articles_7d", region, "en"): _ramp(index)
        for region in ("AE", "SA", "QA")
    }
    _, breadth_one = blended_attention(one_region, index)
    _, breadth_three = blended_attention(three_regions, index)
    assert breadth_three.max() == breadth_one.max() == 1.0


def test_one_chatty_source_cannot_outvote_another():
    """A rising signal duplicated across six series of one source must not
    dominate a falling signal from a second source: net attention stays flat."""
    index = _index()
    rising = _ramp(index)
    falling = {d: -v for d, v in rising.items()}
    series = {("google_news", "articles_7d", r, lang): rising
              for r in ("AE", "SA", "QA") for lang in ("en", "ar")}
    series[("google_trends", "interest", "AE", "en")] = falling
    attention, breadth = blended_attention(series, index)
    assert abs(float(attention.iloc[-1])) < 1e-6
    assert breadth.max() == 1.0  # exactly one of the two sources is up on any day


def test_breadth_still_counts_genuinely_independent_sources():
    index = _index()
    series = {
        ("google_news", "articles_7d", "", "en"): _ramp(index),
        ("google_trends", "interest", "AE", "en"): _ramp(index),
        ("wikipedia_en", "pageviews", "", "en"): _ramp(index),
    }
    _, breadth = blended_attention(series, index)
    assert breadth.max() == 3.0


def test_wikipedia_editions_count_as_one_source():
    assert source_family("wikipedia_ar") == source_family("wikipedia_en") == "wikipedia"
    assert source_family("google_trends") == "google_trends"
    index = _index()
    series = {
        ("wikipedia_en", "pageviews", "", "en"): _ramp(index),
        ("wikipedia_ar", "pageviews", "", "ar"): _ramp(index),
    }
    _, breadth = blended_attention(series, index)
    assert breadth.max() == 1.0


def test_a_silent_series_does_not_dilute_its_own_source():
    """One region spiking while a sibling region is flat should still read as
    that source being active."""
    index = _index()
    series = {
        ("google_trends", "interest", "AE", "en"): _ramp(index),
        ("google_trends", "interest", "SA", "en"): _flat(index),
    }
    attention, breadth = blended_attention(series, index)
    assert float(attention.iloc[-1]) > 0
    assert breadth.iloc[-1] == 1.0
