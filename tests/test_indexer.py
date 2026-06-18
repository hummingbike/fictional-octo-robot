from sbsearch.indexer import (
    file_count,
    index_directory,
    index_file,
    index_roots,
    open_index,
    remove_file,
)


def test_index_directory_indexes_only_known_extensions(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.md").write_text("world")
    (tmp_path / "c.log").write_text("logged")
    (tmp_path / "d.bin").write_text("ignored")  # not a known extension

    con = open_index(tmp_path / "index.db")
    count = index_directory(con, tmp_path)

    assert count == 3
    assert file_count(con) == 3


def test_index_directory_recurses_subfolders(tmp_path):
    sub = tmp_path / "nested" / "deeper"
    sub.mkdir(parents=True)
    (sub / "note.md").write_text("deep content")

    con = open_index(tmp_path / "index.db")
    count = index_directory(con, tmp_path)

    assert count == 1
    row = con.execute("SELECT path FROM files_fts").fetchone()
    assert row[0] == str(sub / "note.md")


def test_index_file_returns_false_when_content_unchanged(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("same content")
    con = open_index(tmp_path / "index.db")

    assert index_file(con, f) is True
    con.commit()
    assert index_file(con, f) is False  # nothing changed, no-op


def test_index_file_reindexes_when_content_changes(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("original content")
    con = open_index(tmp_path / "index.db")
    index_file(con, f)
    con.commit()

    f.write_text("updated content")
    changed = index_file(con, f)
    con.commit()

    assert changed is True
    assert file_count(con) == 1  # re-indexed in place, not duplicated
    row = con.execute("SELECT body FROM files_fts").fetchone()
    assert row[0] == "updated content"


def test_remove_file_deletes_from_index(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("to be removed")
    con = open_index(tmp_path / "index.db")
    index_file(con, f)
    con.commit()

    removed = remove_file(con, f)
    con.commit()

    assert removed is True
    assert file_count(con) == 0


def test_remove_file_returns_false_when_not_indexed(tmp_path):
    con = open_index(tmp_path / "index.db")
    assert remove_file(con, tmp_path / "missing.txt") is False


def test_open_index_creates_missing_parent_directory(tmp_path):
    db_path = tmp_path / "nested" / "deeper" / "index.db"

    con = open_index(db_path)

    assert db_path.parent.is_dir()
    assert file_count(con) == 0


def test_index_directory_skips_excluded_files(tmp_path):
    (tmp_path / "keep.md").write_text("keep me")
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "wip.md").write_text("work in progress")

    con = open_index(tmp_path / "index.db")
    count = index_directory(con, tmp_path, exclude_patterns=["drafts/"])

    assert count == 1
    row = con.execute("SELECT path FROM files_fts").fetchone()
    assert row[0] == str(tmp_path / "keep.md")


def test_index_roots_indexes_each_root(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "one.txt").write_text("one")
    (root_b / "two.txt").write_text("two")

    con = open_index(tmp_path / "index.db")
    count = index_roots(con, [root_a, root_b])

    assert count == 2
    assert file_count(con) == 2


def test_index_roots_applies_excludes_to_every_root(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "keep.txt").write_text("keep")
    (root_a / "skip.tmp.txt").write_text("skip")
    (root_b / "keep.txt").write_text("keep")

    con = open_index(tmp_path / "index.db")
    count = index_roots(con, [root_a, root_b], exclude_patterns=["skip.tmp.*"])

    assert count == 2
    assert file_count(con) == 2
