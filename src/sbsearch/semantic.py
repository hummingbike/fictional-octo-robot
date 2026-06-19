"""Semantic (embedding) search: chunk -> embed -> store -> kNN search (F6, Phase 3).

Vector storage lives in the same SQLite file as the FTS5 index (PLAN.md's
single-file design) via the sqlite-vec extension, but in tables of its own,
set up on demand by `enable_vector_search` rather than by `open_index` --
plain keyword search/index/watch/status stay unaffected by this heavier
dependency unless `--semantic` is actually used.

Merge strategy (decided here, per TODO.md's open question): semantic
results are a separate search mode, not fused with keyword BM25 results.
BM25 rank and cosine similarity aren't on a comparable scale, and the PRD's
non-goal of LLM-based answer synthesis means there's no ranker to learn a
fusion weight from; `--semantic` simply switches the backend.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import sqlite_vec

from sbsearch.chunking import chunk_text
from sbsearch.embeddings import EMBEDDING_DIM, LocalEmbedder
from sbsearch.indexer import DEFAULT_EXTENSIONS, iter_matching_files

_CHUNKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    content_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
"""


def enable_vector_search(con: sqlite3.Connection, dim: int = EMBEDDING_DIM) -> None:
    """Load the sqlite-vec extension and create the chunk/vector tables if missing."""
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)
    con.executescript(_CHUNKS_SCHEMA)
    con.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING "
        f"vec0(chunk_id INTEGER PRIMARY KEY, embedding FLOAT[{dim}] distance_metric=cosine)"
    )


def _hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def remove_chunks(con: sqlite3.Connection, path: Path | str) -> int:
    """Remove a file's chunks and vectors. Returns the number of chunks removed."""
    rows = con.execute("SELECT id FROM chunks WHERE path = ?", (str(path),)).fetchall()
    for (chunk_id,) in rows:
        con.execute("DELETE FROM chunk_vectors WHERE chunk_id = ?", (chunk_id,))
    con.execute("DELETE FROM chunks WHERE path = ?", (str(path),))
    return len(rows)


def index_file_semantic(con: sqlite3.Connection, path: Path, embedder: LocalEmbedder) -> bool:
    """Chunk, embed, and store one file's vectors.

    Returns True if (re)indexed, False if the file's content hash matches
    what's already stored (mirrors indexer.index_file's change detection).
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    content_hash = _hash_text(text)
    path_str = str(path)

    existing = con.execute(
        "SELECT content_hash FROM chunks WHERE path = ? LIMIT 1", (path_str,)
    ).fetchone()
    if existing is not None and existing[0] == content_hash:
        return False

    remove_chunks(con, path_str)
    chunks = chunk_text(text)
    if chunks:
        vectors = embedder.embed(chunks)
        for chunk_index, (chunk, vector) in enumerate(zip(chunks, vectors)):
            cur = con.execute(
                "INSERT INTO chunks(path, chunk_index, text, content_hash) VALUES (?, ?, ?, ?)",
                (path_str, chunk_index, chunk, content_hash),
            )
            con.execute(
                "INSERT INTO chunk_vectors(chunk_id, embedding) VALUES (?, ?)",
                (cur.lastrowid, sqlite_vec.serialize_float32(vector)),
            )
    return True


def index_roots_semantic(
    con: sqlite3.Connection,
    roots: Iterable[Path],
    embedder: LocalEmbedder,
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
    exclude_patterns: tuple[str, ...] | list[str] | None = None,
    max_file_size_bytes: int | None = None,
) -> int:
    """Semantic-index every matching file under `roots`. Returns files (re)indexed."""
    count = 0
    for root in roots:
        for path in iter_matching_files(
            Path(root), extensions, exclude_patterns, max_file_size_bytes
        ):
            if index_file_semantic(con, path, embedder):
                count += 1
    con.commit()
    return count


@dataclass
class SemanticReconcileResult:
    indexed: int  # new or changed files (re)chunked/embedded
    removed: int  # stale chunk sets removed (file no longer exists on disk)


def reconcile_roots_semantic(
    con: sqlite3.Connection,
    roots: Iterable[Path],
    embedder: LocalEmbedder,
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
    exclude_patterns: tuple[str, ...] | list[str] | None = None,
    max_file_size_bytes: int | None = None,
) -> SemanticReconcileResult:
    """Semantic analogue of indexer.reconcile_roots: re-embed changed files and
    drop chunks for files deleted since the last semantic index/watch run."""
    indexed = index_roots_semantic(
        con, roots, embedder, extensions, exclude_patterns, max_file_size_bytes
    )

    removed = 0
    paths = {row[0] for row in con.execute("SELECT DISTINCT path FROM chunks").fetchall()}
    for path_str in paths:
        if not Path(path_str).exists():
            removed += remove_chunks(con, path_str)
    con.commit()

    return SemanticReconcileResult(indexed=indexed, removed=removed)


@dataclass
class SemanticResult:
    path: str
    snippet: str  # the full matched chunk (not a highlighted excerpt, unlike keyword search)
    score: float  # cosine similarity, higher = more similar


def semantic_search(
    con: sqlite3.Connection, query: str, embedder: LocalEmbedder, limit: int = 20
) -> list[SemanticResult]:
    """kNN search over stored chunk embeddings. Index lookup only, no re-embedding of files."""
    (query_vector,) = embedder.embed([query])
    rows = con.execute(
        """
        SELECT c.path, c.text, v.distance
        FROM chunk_vectors v
        JOIN chunks c ON c.id = v.chunk_id
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (sqlite_vec.serialize_float32(query_vector), limit),
    ).fetchall()
    return [SemanticResult(path=row[0], snippet=row[1], score=1 - row[2]) for row in rows]
