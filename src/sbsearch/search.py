"""Query the FTS5 index built by sbsearch.indexer.

FTS5's own query syntax already covers F5 from the PRD almost for free:
implicit AND between bare terms, explicit OR/NOT, "phrase" matching, and
prefix* matching are all native to MATCH, so this module is a thin,
search-time-only layer (no filesystem access, no re-scan) on top of it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

_BODY_COLUMN_INDEX = 1  # files_fts columns: path(0), body(1), ...

_SEARCH_SQL = """
    SELECT path, snippet(files_fts, ?, '>>>', '<<<', '...', 12), rank
    FROM files_fts
    WHERE files_fts MATCH ?
    ORDER BY rank
    LIMIT ?
"""


@dataclass
class SearchResult:
    path: str
    snippet: str
    score: float


def search(con: sqlite3.Connection, query: str, limit: int = 20) -> list[SearchResult]:
    """Run a keyword query against the index. Index lookup only, no I/O on files."""
    rows = con.execute(_SEARCH_SQL, (_BODY_COLUMN_INDEX, query, limit)).fetchall()
    return [SearchResult(path=row[0], snippet=row[1], score=row[2]) for row in rows]
