from trendpulse.importers import import_ga4, import_gsc
from trendpulse.storage import Store


def _cfg(tmp_path):
    return {"imports": {"gsc_dir": str(tmp_path / "gsc"), "ga4_dir": str(tmp_path / "ga4")}}


def test_gsc_import_dated_export(tmp_path):
    gsc = tmp_path / "gsc"
    gsc.mkdir()
    (gsc / "Queries.csv").write_text(
        "Date,Query,Clicks,Impressions,CTR,Position\n"
        "2026-08-01,credit card uae,120,3400,3.5%,4.2\n"
        "2026-08-02,Credit Card UAE,140,3600,3.9%,4.1\n"
        "2026-08-02,كيف أفتح حساب بنكي,55,900,6.1%,2.0\n"
    )
    store = Store(tmp_path / "t.db")
    written = import_gsc(store, _cfg(tmp_path))
    assert written == 6  # 3 rows x (clicks + impressions)
    series = store.series("credit card uae")
    # upsert is idempotent per (date, source, metric): duplicate keyword casing merged
    assert series[("gsc", "clicks", "", "")]["2026-08-02"] == 140.0
    assert ("gsc", "impressions", "", "") in store.series("كيف أفتح حساب بنكي")
    store.close()


def test_gsc_import_aggregate_export_without_dates(tmp_path):
    gsc = tmp_path / "gsc"
    gsc.mkdir()
    (gsc / "gsc_2026-07-01_2026-07-28.csv").write_text(
        "Top queries,Clicks,Impressions\n"
        "personal loan uae,300,9000\n"
    )
    store = Store(tmp_path / "t.db")
    written = import_gsc(store, _cfg(tmp_path))
    assert written == 2
    series = store.series("personal loan uae")
    # attributed to the export end date from the filename
    assert series[("gsc", "impressions", "", "")] == {"2026-07-28": 9000.0}
    store.close()


def test_gsc_missing_dir_is_noop(tmp_path):
    store = Store(tmp_path / "t.db")
    assert import_gsc(store, _cfg(tmp_path)) == 0
    store.close()


def test_ga4_import_landing_pages(tmp_path):
    ga4 = tmp_path / "ga4"
    ga4.mkdir()
    (ga4 / "landing-pages.csv").write_text(
        "Landing page,Sessions,Total users\n"
        "/en/cards/personal-loan/,500,420\n"
        "/ar/التمويل-الشخصي/,200,180\n"
    )
    store = Store(tmp_path / "t.db")
    written = import_ga4(store, _cfg(tmp_path))
    assert written == 2
    series = store.series("cards personal loan")  # locale segment dropped
    assert ("ga4", "organic_sessions", "", "") in series
    store.close()
