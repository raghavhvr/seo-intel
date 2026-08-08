from trendpulse.storage import Store
from trendpulse.types import Discovery, Observation


def test_roundtrip(tmp_path):
    store = Store(tmp_path / "test.db")
    store.upsert_observations([
        Observation(date="2026-08-01", keyword="crm", source="s1", metric="m1", value=1.0),
        Observation(date="2026-08-02", keyword="crm", source="s1", metric="m1", value=2.0),
        Observation(date="2026-08-02", keyword="crm", source="s2", metric="m2", value=5.0),
    ])
    store.upsert_discoveries([
        Discovery(date="2026-08-02", keyword="crm pricing", source="s1", context="ctx", score=9.0),
    ])

    series = store.series("crm")
    assert series[("s1", "m1", "", "")] == {"2026-08-01": 1.0, "2026-08-02": 2.0}
    assert ("s2", "m2", "", "") in series
    assert store.dates() == ["2026-08-01", "2026-08-02"]
    assert "crm" in store.observed_keywords()
    assert store.discovered_keywords()[0][0] == "crm pricing"

    # upsert replaces rather than duplicates
    store.upsert_observations([
        Observation(date="2026-08-02", keyword="crm", source="s1", metric="m1", value=3.0),
    ])
    assert store.series("crm")[("s1", "m1", "", "")]["2026-08-02"] == 3.0

    store.save_score("2026-08-02", "crm", "week", "seo", 88.0, 0.4, 1.2)
    top = store.latest_scores("2026-08-02", "week", "seo")
    assert top[0][0] == "crm" and top[0][1] == 88.0
    store.close()
