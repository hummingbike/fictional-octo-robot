from pathlib import Path

from sbsearch.indexer import (
    file_count,
    index_directory,
    index_file,
    index_roots,
    iter_matching_files,
    open_index,
    reconcile_roots,
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


def test_iter_matching_files_filters_extensions_and_excludes(tmp_path):
    (tmp_path / "keep.md").write_text("keep")
    (tmp_path / "ignored.bin").write_text("ignored")
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    (drafts / "wip.md").write_text("wip")

    found = list(iter_matching_files(tmp_path, exclude_patterns=["drafts/"]))

    assert found == [tmp_path / "keep.md"]


def test_iter_matching_files_skips_files_over_max_size(tmp_path):
    small = tmp_path / "small.txt"
    large = tmp_path / "large.txt"
    small.write_text("x" * 10)
    large.write_text("x" * 1000)

    found = list(iter_matching_files(tmp_path, max_file_size_bytes=100))

    assert found == [small]


def test_iter_matching_files_no_size_limit_by_default(tmp_path):
    large = tmp_path / "large.txt"
    large.write_text("x" * 1000)

    found = list(iter_matching_files(tmp_path))

    assert found == [large]


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


def test_open_index_allows_use_from_another_thread(tmp_path):
    import threading

    db_path = tmp_path / "index.db"
    con = open_index(db_path, check_same_thread=False)
    errors = []

    def write_from_other_thread():
        try:
            f = tmp_path / "note.txt"
            f.write_text("from another thread")
            index_file(con, f)
            con.commit()
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    t = threading.Thread(target=write_from_other_thread)
    t.start()
    t.join()

    assert errors == []
    assert file_count(con) == 1


def test_reconcile_roots_indexes_new_and_changed_files(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("original")
    con = open_index(tmp_path / "index.db")
    index_directory(con, root)

    (root / "a.txt").write_text("changed")
    (root / "b.txt").write_text("new file")

    result = reconcile_roots(con, [root])

    assert result.indexed == 2  # a.txt re-indexed (changed), b.txt newly indexed
    assert result.removed == 0
    assert file_count(con) == 2


def test_reconcile_roots_removes_entries_for_deleted_files(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    keep = root / "keep.txt"
    gone = root / "gone.txt"
    keep.write_text("keep me")
    gone.write_text("delete me")
    con = open_index(tmp_path / "index.db")
    index_directory(con, root)
    assert file_count(con) == 2

    gone.unlink()

    result = reconcile_roots(con, [root])

    assert result.removed == 1
    assert file_count(con) == 1
    row = con.execute("SELECT path FROM files_fts").fetchone()
    assert row[0] == str(keep)


def test_index_directory_skips_oversized_files(tmp_path):
    (tmp_path / "small.txt").write_text("x" * 10)
    (tmp_path / "huge.log").write_text("x" * 1000)
    con = open_index(tmp_path / "index.db")

    count = index_directory(con, tmp_path, max_file_size_bytes=100)

    assert count == 1
    assert file_count(con) == 1
    row = con.execute("SELECT path FROM files_fts").fetchone()
    assert row[0] == str(tmp_path / "small.txt")


def test_reconcile_roots_passes_through_max_file_size(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "small.txt").write_text("x" * 10)
    (root / "huge.log").write_text("x" * 1000)
    con = open_index(tmp_path / "index.db")

    result = reconcile_roots(con, [root], max_file_size_bytes=100)

    assert result.indexed == 1
    assert file_count(con) == 1


def test_index_file_skips_file_deleted_before_read(tmp_path):
    f = tmp_path / "ghost.txt"
    f.write_text("will vanish")
    con = open_index(tmp_path / "index.db")
    f.unlink()  # simulate a race: listed, then removed before index_file reads it

    assert index_file(con, f) is False
    assert file_count(con) == 0


def test_index_file_skips_unreadable_file(tmp_path, monkeypatch):
    f = tmp_path / "locked.txt"
    f.write_text("secret")
    con = open_index(tmp_path / "index.db")

    def deny(self, *args, **kwargs):
        raise PermissionError(self)

    monkeypatch.setattr(Path, "read_text", deny)

    assert index_file(con, f) is False
    assert file_count(con) == 0


def test_index_directory_continues_after_a_file_disappears_mid_scan(tmp_path, monkeypatch):
    keep = tmp_path / "keep.txt"
    vanish = tmp_path / "vanish.txt"
    keep.write_text("keep me")
    vanish.write_text("will be deleted")
    con = open_index(tmp_path / "index.db")

    original_read_text = Path.read_text

    def flaky_read_text(self, *args, **kwargs):
        if self.name == "vanish.txt":
            raise FileNotFoundError(self)
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)

    index_directory(con, tmp_path)

    assert file_count(con) == 1
    row = con.execute("SELECT path FROM files_fts").fetchone()
    assert row[0] == str(keep)


def test_iter_matching_files_skips_file_that_vanishes_before_size_check(tmp_path, monkeypatch):
    keep = tmp_path / "keep.txt"
    vanish = tmp_path / "vanish.txt"
    keep.write_text("x")
    vanish.write_text("y")

    # Pin is_file() to "yes, it's a file" for vanish.txt -- as it genuinely
    # was when rglob listed it -- so the race is isolated to the later,
    # separate stat() call iter_matching_files makes for the size check.
    # (Patching only Path.stat isn't reliable here: is_file()'s own
    # FileNotFoundError handling differs across Python versions, and on
    # some it doesn't even route through the patched bound method.)
    original_is_file = Path.is_file
    original_stat = Path.stat

    def fake_is_file(self, *args, **kwargs):
        if self.name == "vanish.txt":
            return True
        return original_is_file(self, *args, **kwargs)

    def flaky_stat(self, *args, **kwargs):
        if self.name == "vanish.txt":
            raise FileNotFoundError(2, "No such file or directory", str(self))
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "is_file", fake_is_file)
    monkeypatch.setattr(Path, "stat", flaky_stat)

    found = list(iter_matching_files(tmp_path, max_file_size_bytes=100))

    assert found == [keep]


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
