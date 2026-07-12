"""Query the FTS5 index built by sbsearch.indexer.

FTS5's own query syntax already covers F5 from the PRD almost for free:
implicit AND between bare terms, explicit OR/NOT, "phrase" matching, and
prefix* matching are all native to MATCH, so this module is a thin,
search-time-only layer (no filesystem access, no re-scan) on top of it.

One rewrite is applied before MATCH: queries that use none of the FTS5
syntax (no quotes/operators/wildcards) have each term turned into a quoted
prefix query (`예산안` → `"예산안"*`). unicode61 tokenizes Korean by
whitespace, so an inflected token like `예산안을` is never equal to the
bare term the user types — prefix matching is what makes the tool's primary
use case (Korean notes, agglutinative suffixes) work at all. Queries that
do use FTS5 syntax are passed through verbatim, preserving full operator
control.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

_FTS5_SYNTAX_CHARS = set('"*():^+{}')
_FTS5_OPERATORS = {"AND", "OR", "NOT", "NEAR"}

_BODY_COLUMN_INDEX = 1  # files_fts columns: path(0), body(1), ...

_SEARCH_SQL = """
    SELECT path, snippet(files_fts, ?, '>>>', '<<<', '...', ?), rank
    FROM files_fts
    WHERE files_fts MATCH ?
    ORDER BY rank
    LIMIT ?
"""

DEFAULT_CONTEXT_TOKENS = 12


@dataclass
class SearchResult:
    path: str
    snippet: str
    score: float


def _is_plain_query(query: str) -> bool:
    """True if the query uses no FTS5 syntax and is safe to rewrite."""
    if any(ch in _FTS5_SYNTAX_CHARS for ch in query):
        return False
    return not any(token in _FTS5_OPERATORS for token in query.split())


def _as_prefix_query(query: str) -> str:
    """Rewrite each bare term to a quoted prefix query (implicit AND between terms)."""
    return " ".join(f'"{term}"*' for term in query.split())


def search(
    con: sqlite3.Connection,
    query: str,
    limit: int = 20,
    context_tokens: int = DEFAULT_CONTEXT_TOKENS,
) -> list[SearchResult]:
    """Run a keyword query against the index. Index lookup only, no I/O on files.

    `context_tokens` controls how many tokens of surrounding context FTS5
    includes around each match in the snippet (the FTS5 analogue of `grep -C`,
    since results are token-bounded snippets rather than re-read source lines).

    Plain queries (no FTS5 operators/quotes/wildcards) are rewritten to
    per-term prefix matches so bare Korean terms match their inflected
    occurrences; see the module docstring.
    """
    if _is_plain_query(query):
        query = _as_prefix_query(query)
    rows = con.execute(
        _SEARCH_SQL, (_BODY_COLUMN_INDEX, context_tokens, query, limit)
    ).fetchall()
    return [SearchResult(path=row[0], snippet=row[1], score=row[2]) for row in rows]
