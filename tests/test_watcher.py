import time

from sbsearch.indexer import file_count, index_directory, open_index
from sbsearch.watcher import Debouncer, IndexWatcher


def _wait_until(predicate, timeout=5.0, interval=0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_debouncer_coalesces_rapid_calls_into_one_action():
    debouncer = Debouncer(delay=0.1)
    calls = []

    for _ in range(5):
        debouncer.schedule("same-key", lambda: calls.append(1))
        time.sleep(0.02)  # well under the debounce delay

    debouncer.wait_idle(timeout=2.0)

    assert calls == [1]


def test_debouncer_runs_each_distinct_key_independently():
    debouncer = Debouncer(delay=0.05)
    calls = []

    debouncer.schedule("a", lambda: calls.append("a"))
    debouncer.schedule("b", lambda: calls.append("b"))
    debouncer.wait_idle(timeout=2.0)

    assert sorted(calls) == ["a", "b"]


def test_watcher_indexes_newly_created_file(tmp_path):
    root = (tmp_path / "root").resolve()
    root.mkdir()
    con = open_index(tmp_path / "index.db", check_same_thread=False)

    watcher = IndexWatcher(con, [root], debounce_seconds=0.05)
    watcher.start()
    try:
        (root / "new.txt").write_text("hello fox")
        assert _wait_until(lambda: file_count(con) == 1)
    finally:
        watcher.stop()


def test_watcher_reindexes_modified_file(tmp_path):
    root = (tmp_path / "root").resolve()
    root.mkdir()
    target = root / "note.txt"
    target.write_text("original")
    con = open_index(tmp_path / "index.db", check_same_thread=False)
    index_directory(con, root)

    watcher = IndexWatcher(con, [root], debounce_seconds=0.05)
    watcher.start()
    try:
        target.write_text("updated content")

        def body_updated():
            row = con.execute("SELECT body FROM files_fts WHERE path = ?", (str(target),)).fetchone()
            return row is not None and row[0] == "updated content"

        assert _wait_until(body_updated)
    finally:
        watcher.stop()


def test_watcher_removes_deleted_file(tmp_path):
    root = (tmp_path / "root").resolve()
    root.mkdir()
    target = root / "note.txt"
    target.write_text("to be removed")
    con = open_index(tmp_path / "index.db", check_same_thread=False)
    index_directory(con, root)
    assert file_count(con) == 1

    watcher = IndexWatcher(con, [root], debounce_seconds=0.05)
    watcher.start()
    try:
        target.unlink()
        assert _wait_until(lambda: file_count(con) == 0)
    finally:
        watcher.stop()


def test_watcher_reindexes_moved_file_under_new_path(tmp_path):
    root = (tmp_path / "root").resolve()
    root.mkdir()
    old_path = root / "old.txt"
    new_path = root / "new.txt"
    old_path.write_text("moved content")
    con = open_index(tmp_path / "index.db", check_same_thread=False)
    index_directory(con, root)

    watcher = IndexWatcher(con, [root], debounce_seconds=0.05)
    watcher.start()
    try:
        old_path.rename(new_path)

        def moved():
            paths = {row[0] for row in con.execute("SELECT path FROM files_fts").fetchall()}
            return paths == {str(new_path)}

        assert _wait_until(moved)
    finally:
        watcher.stop()


def test_watcher_ignores_files_with_unmatched_extension(tmp_path):
    root = (tmp_path / "root").resolve()
    root.mkdir()
    con = open_index(tmp_path / "index.db", check_same_thread=False)

    watcher = IndexWatcher(con, [root], debounce_seconds=0.05)
    watcher.start()
    try:
        (root / "ignored.bin").write_text("not indexed")
        time.sleep(0.5)  # give the watcher a chance to (wrongly) react
        assert file_count(con) == 0
    finally:
        watcher.stop()


def test_watcher_respects_exclude_patterns(tmp_path):
    root = (tmp_path / "root").resolve()
    drafts = root / "drafts"
    drafts.mkdir(parents=True)
    con = open_index(tmp_path / "index.db", check_same_thread=False)

    watcher = IndexWatcher(con, [root], exclude_patterns=["drafts/"], debounce_seconds=0.05)
    watcher.start()
    try:
        (root / "keep.txt").write_text("keep me")
        assert _wait_until(lambda: file_count(con) == 1)
        (drafts / "wip.txt").write_text("excluded")
        time.sleep(0.5)
        assert file_count(con) == 1
    finally:
        watcher.stop()
