from sbsearch.indexer import index_file, open_index
from sbsearch.status import get_status


def test_status_on_empty_index(tmp_path):
    db_path = tmp_path / "index.db"
    con = open_index(db_path)

    status = get_status(con, db_path)

    assert status.file_count == 0
    assert status.last_indexed is None
    assert status.db_size_bytes > 0  # the empty FTS5 schema still occupies space


def test_status_reflects_indexed_files(tmp_path):
    db_path = tmp_path / "index.db"
    con = open_index(db_path)
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("alpha")
    f2.write_text("beta")
    index_file(con, f1)
    index_file(con, f2)
    con.commit()

    status = get_status(con, db_path)

    assert status.file_count == 2
    assert status.last_indexed == max(f1.stat().st_mtime, f2.stat().st_mtime)


def test_status_db_size_zero_for_missing_path(tmp_path):
    db_path = tmp_path / "index.db"
    con = open_index(db_path)

    status = get_status(con, tmp_path / "does-not-exist.db")

    assert status.db_size_bytes == 0
