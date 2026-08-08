import zipfile

from trendpulse.importers import import_ga4, import_gsc
from trendpulse.storage import Store


def _cfg(tmp_path):
    return {"imports": {"gsc_dir": str(tmp_path / "gsc"), "ga4_dir": str(tmp_path / "ga4")}}


def _gsc_zip(path, queries_csv):
    """A GSC export zip as the UI actually delivers it — Queries.csv plus
    sibling reports that have no query column and must be skipped."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Queries.csv", queries_csv)
        zf.writestr("Countries.csv", "Country,Clicks,Impressions\nare,500,9000\n")
        zf.writestr("Devices.csv", "Device,Clicks,Impressions\nMOBILE,400,7000\n")


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


def test_gsc_zip_import_with_month_in_filename(tmp_path):
    """Drop the zip exactly as GSC hands it over — no unzipping, no renaming.
    'GSC-Search-Performance-Jul-26.zip' dates its aggregate rows to July 2026's
    last day; members without a query column (Countries, Devices) are skipped."""
    gsc = tmp_path / "gsc"
    gsc.mkdir()
    _gsc_zip(gsc / "GSC-Search-Performance-Jul-26.zip",
             "Top queries,Clicks,Impressions\ncredit card uae,300,9000\n")
    _gsc_zip(gsc / "GSC-Search-Performance-Oct-25.zip",
             "Top queries,Clicks,Impressions\ncredit card uae,220,7500\n")
    store = Store(tmp_path / "t.db")
    assert import_gsc(store, _cfg(tmp_path)) == 4
    series = store.series("credit card uae")
    assert series[("gsc", "impressions", "", "")] == {
        "2026-07-31": 9000.0, "2025-10-31": 7500.0}
    store.close()


def test_gsc_generative_ai_export_gets_its_own_source(tmp_path):
    """The Generative-AI report is a subset of search performance. Same-month
    imports under one source would overwrite each other on the observations
    primary key — and the AI subset is GEO ground truth worth keeping apart."""
    gsc = tmp_path / "gsc"
    gsc.mkdir()
    _gsc_zip(gsc / "GSC-Search-Performance-Jul-26.zip",
             "Top queries,Clicks,Impressions\nbest bank uae,300,9000\n")
    _gsc_zip(gsc / "GSC-Generative-AI-Jul-26.zip",
             "Top queries,Clicks,Impressions\nbest bank uae,12,400\n")
    store = Store(tmp_path / "t.db")
    import_gsc(store, _cfg(tmp_path))
    series = store.series("best bank uae")
    assert series[("gsc", "impressions", "", "")] == {"2026-07-31": 9000.0}
    assert series[("gsc_ai", "impressions", "", "")] == {"2026-07-31": 400.0}
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
