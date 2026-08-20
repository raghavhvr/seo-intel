"""The DB travels through git as a gzip snapshot — GitHub rejects files over
100 MB and the raw DB crossed that line. These tests pin the three properties
the workflows rely on: pack/unpack round-trips, packing is deterministic (an
unchanged DB never shows as a git diff), and pruning caps table growth."""
from pathlib import Path

from trendpulse.storage import Store, pack_db, unpack_db


def _make_store(tmp_path: Path) -> Path:
    db = tmp_path / "trendpulse.db"
    store = Store(db)
    store.conn.execute(
        "INSERT INTO citations (date, url, domain, prompt, model)"
        " VALUES ('2020-01-01', 'https://x.com/a', 'x.com', 'old prompt', 'm'),"
        "        (date('now'), 'https://x.com/b', 'x.com', 'new prompt', 'm')")
    store.conn.execute(
        "INSERT INTO observations (date, keyword, source, metric, value)"
        " VALUES (date('now'), 'personal loan uae', 'reddit', 'posts_7d', 3)")
    store.conn.commit()
    store.close()
    return db


def test_pack_unpack_round_trip(tmp_path):
    db = _make_store(tmp_path)
    gz = pack_db(db)
    assert gz == Path(str(db) + ".gz") and gz.exists()

    db.unlink()  # fresh-checkout situation: only the .gz exists
    store = Store(db)  # must auto-inflate
    n = store.conn.execute("SELECT COUNT(*) FROM citations").fetchone()[0]
    store.close()
    assert n == 2


def test_pack_is_deterministic(tmp_path):
    db = _make_store(tmp_path)
    first = pack_db(db).read_bytes()
    second = pack_db(db).read_bytes()
    assert first == second


def test_prune_drops_only_stale_rows(tmp_path):
    db = _make_store(tmp_path)
    store = Store(db)
    deleted = store.prune({"citations": 60})
    rows = store.conn.execute("SELECT prompt FROM citations").fetchall()
    store.close()
    assert deleted == 1
    assert rows == [("new prompt",)]


def test_prune_ignores_unknown_tables_and_zero_windows(tmp_path):
    db = _make_store(tmp_path)
    store = Store(db)
    deleted = store.prune({"citations": 0, "scores": 1, "translations": 1})
    n = store.conn.execute("SELECT COUNT(*) FROM citations").fetchone()[0]
    store.close()
    assert n == 2  # citations disabled; other tables never eligible
    assert deleted == 0
