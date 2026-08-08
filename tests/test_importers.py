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


def test_gsc_generative_ai_export_imports_pages_as_topics(tmp_path):
    """The real Generative-AI zip has NO Queries.csv (verified against the
    ADCB exports: Chart/Pages/Countries/Devices/Filters only). Its Pages.csv —
    which pages surface in AI Overviews — imports as topic keywords under
    source `gsc_ai`, kept apart from `gsc` so same-month imports can't
    overwrite each other on the observations primary key."""
    gsc = tmp_path / "gsc"
    gsc.mkdir()
    _gsc_zip(gsc / "GSC-Search-Performance-Jul-26.zip",
             "Top queries,Clicks,Impressions\nbest bank uae,300,9000\n")
    with zipfile.ZipFile(gsc / "GSC-Generative-AI-Jul-26.zip", "w") as zf:
        zf.writestr("Chart.csv", "Date,Impressions\n2026-07-01,120\n")
        zf.writestr("Pages.csv",
                    "Top pages,Impressions\n"
                    "https://www.adcb.com/en/personal-banking/cards/credit-cards/,400\n")
        zf.writestr("Countries.csv", "Country,Impressions\nare,500\n")
        zf.writestr("Filters.csv", "Filter,Value\nDate,\"Jul 1, 2026-Jul 31, 2026\"\n")
    store = Store(tmp_path / "t.db")
    import_gsc(store, _cfg(tmp_path))
    assert store.series("best bank uae")[("gsc", "impressions", "", "")] == {
        "2026-07-31": 9000.0}
    # full URL -> topic ('en' locale segment dropped, last 3 path parts kept)
    topic = "personal banking cards credit cards"
    assert store.series(topic)[("gsc_ai", "impressions", "", "")] == {
        "2026-07-31": 400.0}
    store.close()


def test_gsc_missing_dir_is_noop(tmp_path):
    store = Store(tmp_path / "t.db")
    assert import_gsc(store, _cfg(tmp_path)) == 0
    store.close()


def test_ga4_import_skips_comment_preamble(tmp_path):
    """GA4 UI exports open with '# …' comment lines before the header. They
    must be skipped, or the file silently imports zero rows."""
    ga4 = tmp_path / "ga4"
    ga4.mkdir()
    (ga4 / "GA4-Landing-Pages-Jul-26.csv").write_text(
        "# ----------------------------------------\n"
        "# All Users\n"
        "# Landing page + query string\n"
        "# 20260701-20260731\n"
        "# ----------------------------------------\n"
        "Landing page + query string,Sessions,Total users\n"
        "/en/cards/personal-loan/,500,420\n"
    )
    store = Store(tmp_path / "t.db")
    assert import_ga4(store, _cfg(tmp_path)) == 1
    series = store.series("cards personal loan")
    # month-style filename dates the aggregate rows (Jul-26 -> month end)
    assert series[("ga4", "organic_sessions", "", "")] == {"2026-07-31": 500.0}
    store.close()


def test_ga4_free_form_monthly_export(tmp_path):
    """The real GA4 'Free form' export (verified against ADCB samples): bare
    Month column with the year only in the '#' preamble range (crossing a year
    boundary), rows per page x channel needing organic filtering + summing,
    and a Grand total row to skip."""
    ga4 = tmp_path / "ga4"
    ga4.mkdir()
    (ga4 / "20260805152159_GA4 Oct 2025 - Feb 2026.csv").write_text(
        "# ----------------------------------------\n"
        "# All Users\n"
        "# 20251001-20260228\n"
        "# ----------------------------------------\n"
        "Month,Landing page,Session default channel group,Sessions\n"
        "10,/en/cards/personal-loan/,Organic Search,100\n"
        "10,/en/cards/personal-loan/,Organic Search,40\n"     # second source/medium
        "10,/en/cards/personal-loan/,Direct,999\n"            # not search demand
        "01,/en/cards/personal-loan/,Organic Search,30\n"     # next year (2026)
        "Grand total,,,1169\n"
    )
    store = Store(tmp_path / "t.db")
    import_ga4(store, _cfg(tmp_path))
    series = store.series("cards personal loan")[("ga4", "organic_sessions", "", "")]
    assert series == {"2025-10-31": 140.0, "2026-01-31": 30.0}
    store.close()


def test_dates_without_dashes_are_normalized(tmp_path):
    """GA4 writes dates as bare '20260301'; stored verbatim they'd coexist
    with '2026-03-01' keys from every other source and split days in two."""
    ga4 = tmp_path / "ga4"
    ga4.mkdir()
    (ga4 / "export.csv").write_text(
        "Date,Landing page,Sessions\n20260301,/en/cards/,500\n")
    store = Store(tmp_path / "t.db")
    import_ga4(store, _cfg(tmp_path))
    assert store.series("cards")[("ga4", "organic_sessions", "", "")] == {
        "2026-03-01": 500.0}
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
