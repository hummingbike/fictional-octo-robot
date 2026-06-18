"""SQLite FTS5-backed full-text index over a set of text files.

Design follows BENCHMARK_EVERYTHING.md's core principle: all expensive work
(reading + tokenizing file content) happens here, at index time, so search
queries are pure index lookups with no filesystem re-scan.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from sbsearch.excludes import build_pathspec, is_excluded

DEFAULT_EXTENSIONS = (".txt", ".md", ".log")

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    path,
    body,
    mtime UNINDEXED,
    size UNINDEXED,
    content_hash UNINDEXED,
    tokenize = 'unicode61'
);
"""


def open_index(db_path: str | Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open (creating if needed) the FTS5 index database at `db_path`.

    `check_same_thread=False` is needed by the watcher (F3), whose debounced
    re-index calls run on timer threads rather than the thread that opened
    the connection; callers doing that must serialize writes themselves.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, check_same_thread=check_same_thread)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(_SCHEMA)
    return con


def _hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def index_file(con: sqlite3.Connection, path: Path) -> bool:
    """Index or re-index a single file.

    Returns True if the index was changed (new file, or content differs from
    what's already indexed); False if the existing entry is already current.
    Caller is responsible for committing.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    content_hash = _hash_text(text)
    stat = path.stat()
    path_str = str(path)

    row = con.execute(
        "SELECT rowid, content_hash FROM files_fts WHERE path = ?", (path_str,)
    ).fetchone()

    if row is not None:
        rowid, existing_hash = row
        if existing_hash == content_hash:
            return False
        con.execute("DELETE FROM files_fts WHERE rowid = ?", (rowid,))

    con.execute(
        "INSERT INTO files_fts(path, body, mtime, size, content_hash) "
        "VALUES (?, ?, ?, ?, ?)",
        (path_str, text, stat.st_mtime, stat.st_size, content_hash),
    )
    return True


def remove_file(con: sqlite3.Connection, path: Path | str) -> bool:
    """Remove a file's entry from the index. Returns True if a row was removed."""
    cur = con.execute("DELETE FROM files_fts WHERE path = ?", (str(path),))
    return cur.rowcount > 0


def iter_matching_files(
    root: Path,
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
    exclude_patterns: tuple[str, ...] | list[str] | None = None,
) -> Iterator[Path]:
    """Walk `root`, yielding files matching `extensions` and not excluded.

    Shared by the keyword indexer and the semantic (chunk/embed) indexer so
    both apply identical root/extension/exclude filtering (F1).
    """
    spec = build_pathspec(exclude_patterns) if exclude_patterns else None
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in extensions:
            continue
        if spec is not None and is_excluded(spec, root, path):
            continue
        yield path


def index_directory(
    con: sqlite3.Connection,
    root: Path,
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
    exclude_patterns: tuple[str, ...] | list[str] | None = None,
) -> int:
    """Walk `root` and index every file matching `extensions`.

    Files matching `exclude_patterns` (.gitignore-style, relative to `root`)
    are skipped. Commits once at the end. Returns the number of files processed.
    """
    count = 0
    for path in iter_matching_files(root, extensions, exclude_patterns):
        index_file(con, path)
        count += 1
    con.commit()
    return count


def index_roots(
    con: sqlite3.Connection,
    roots: Iterable[Path],
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
    exclude_patterns: tuple[str, ...] | list[str] | None = None,
) -> int:
    """Index multiple root folders (F1), applying the same exclude patterns to each."""
    return sum(
        index_directory(con, root, extensions, exclude_patterns) for root in roots
    )


def file_count(con: sqlite3.Connection) -> int:
    return con.execute("SELECT count(*) FROM files_fts").fetchone()[0]


@dataclass
class ReconcileResult:
    indexed: int  # new or changed files (re)indexed
    removed: int  # stale entries removed (file no longer exists on disk)


def reconcile_roots(
    con: sqlite3.Connection,
    roots: Iterable[Path],
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
    exclude_patterns: tuple[str, ...] | list[str] | None = None,
) -> ReconcileResult:
    """Bring the index back in sync with the filesystem (F3 restart recovery).

    Re-walks `roots` (index_file's hash check makes this a no-op for files
    that haven't changed) and removes index entries whose file no longer
    exists -- covering deletes/moves that happened while no watcher was
    running, e.g. after a crash or before the first `watch` invocation.
    """
    indexed = index_roots(con, roots, extensions, exclude_patterns)

    removed = 0
    for (path_str,) in con.execute("SELECT path FROM files_fts").fetchall():
        if not Path(path_str).exists():
            remove_file(con, path_str)
            removed += 1
    con.commit()

    return ReconcileResult(indexed=indexed, removed=removed)
