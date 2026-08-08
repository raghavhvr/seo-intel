from datetime import date

from trendpulse.keywords import (is_question, is_relevant, normalize,
                                 universe_tokens, valid_candidate)
from trendpulse.seasonality import load_events, prep_keywords, upcoming_events
from trendpulse.storage import Store
from trendpulse.types import Observation

GEO_CFG = {"geo_terms": ["ai", "fintech"]}

CFG = {
    "seasonal_events": [
        {"name": "Back to school (UAE)", "start": "2026-08-24", "prep_weeks": 4,
         "regions": ["AE"], "keywords": ["school fee payment plan uae"],
         "action": "publish early"},
        {"name": "Ramadan", "start": "2027-02-07", "end": "2027-03-08",
         "prep_weeks": 6, "expected": True, "keywords": ["ramadan bank offers uae"]},
    ],
}


def test_arabic_normalize():
    assert normalize("قرض شخصي الإمارات!") == "قرض شخصي الإمارات"
    assert normalize("بطاقة ائتمان مع تشكيل مُجَرَّد") == "بطاقة ائتمان مع تشكيل مجرد"
    assert valid_candidate(normalize("قرض شخصي الإمارات"))


def test_arabic_questions():
    assert is_question("كيف أفتح حساب بنكي في الإمارات")
    assert is_question("هل التمويل الإسلامي حلال")
    assert is_question("ما هو الحد الأدنى للراتب")
    assert not is_question("قرض شخصي الإمارات")


def test_seasonality_windows():
    today = date(2026, 8, 7)
    events = upcoming_events(CFG, today, within_days=90)
    assert [e.name for e in events] == ["Back to school (UAE)"]  # Ramadan is ~184d out
    assert events[0].in_prep_window(today)
    far = upcoming_events(CFG, today, within_days=200)
    assert [e.name for e in far] == ["Back to school (UAE)", "Ramadan"]

    # during Ramadan prep window the Ramadan keywords surface
    jan = date(2027, 1, 15)
    assert any("ramadan" in kw for kw, _ in prep_keywords(CFG, jan))
    assert not any("ramadan" in kw for kw, _ in prep_keywords(CFG, today))

    # active during the event itself
    ramadan = date(2027, 2, 20)
    assert any(e.is_active(ramadan) for e in load_events(CFG))


def test_relevance_gate():
    tokens = universe_tokens(["credit card uae", "personal loan uae",
                              "bank account uae", "قرض شخصي"])
    assert is_relevant("best credit card offers uae", tokens, GEO_CFG)     # token overlap
    assert is_relevant("how to open a bank account", tokens, GEO_CFG)      # question + overlap
    assert is_relevant("ai banking platforms", tokens, GEO_CFG)            # geo term
    assert not is_relevant("so paulo urban forest", tokens, GEO_CFG)       # front-page noise
    assert not is_relevant("which gym is this", tokens, GEO_CFG)           # off-topic question


def test_observation_region_language_roundtrip(tmp_path):
    store = Store(tmp_path / "t.db")
    store.upsert_observations([
        Observation(date="2026-08-01", keyword="credit card uae", source="google_trends",
                    metric="interest", value=55.0, region="AE", language="en"),
        Observation(date="2026-08-01", keyword="credit card uae", source="google_trends",
                    metric="interest", value=30.0, region="SA", language="en"),
        Observation(date="2026-08-01", keyword="credit card uae", source="google_news",
                    metric="articles_7d", value=12.0, region="AE", language="ar"),
    ])
    series = store.series("credit card uae")
    assert series[("google_trends", "interest", "AE", "en")] == {"2026-08-01": 55.0}
    assert series[("google_trends", "interest", "SA", "en")] == {"2026-08-01": 30.0}
    assert series[("google_news", "articles_7d", "AE", "ar")] == {"2026-08-01": 12.0}
    store.close()
