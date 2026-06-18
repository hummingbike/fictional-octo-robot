"""Tests for sqlite-vec-backed chunk storage/search using a fake embedder.

The real embedding model is exercised separately in test_embeddings.py;
here we want fast, deterministic coverage of the storage/retrieval logic
itself (chunking integration, hash-based skip, removal, kNN ranking), so
a hashed bag-of-words stand-in replaces the real ONNX model.
"""

import hashlib
import math

from sbsearch.embeddings import EMBEDDING_DIM
from sbsearch.indexer import open_index
from sbsearch.semantic import (
    enable_vector_search,
    index_file_semantic,
    index_roots_semantic,
    reconcile_roots_semantic,
    remove_chunks,
    semantic_search,
)


class FakeEmbedder:
    """Deterministic hashed bag-of-words embedding: shared words => closer vectors."""

    def embed(self, texts):
        return [self._vector_for(text) for text in texts]

    def _vector_for(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIM
        for word in text.lower().split():
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
            vector[index] += 1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]


def _open(tmp_path):
    con = open_index(tmp_path / "index.db")
    enable_vector_search(con)
    return con


def test_index_file_semantic_stores_chunks_and_vectors(tmp_path):
    con = _open(tmp_path)
    f = tmp_path / "note.txt"
    # two paragraphs, each under max_chars (800) alone, but too big combined,
    # so chunk_text keeps them as two separate (non-sliced) chunks
    f.write_text(("a" * 500) + "\n\n" + ("b" * 500))

    changed = index_file_semantic(con, f, FakeEmbedder())
    con.commit()

    assert changed is True
    chunk_rows = con.execute("SELECT path, chunk_index, text FROM chunks").fetchall()
    assert len(chunk_rows) == 2
    vector_rows = con.execute("SELECT count(*) FROM chunk_vectors").fetchone()
    assert vector_rows[0] == 2


def test_index_file_semantic_skips_unchanged_content(tmp_path):
    con = _open(tmp_path)
    f = tmp_path / "note.txt"
    f.write_text("stable content")
    index_file_semantic(con, f, FakeEmbedder())
    con.commit()

    changed = index_file_semantic(con, f, FakeEmbedder())
    con.commit()

    assert changed is False
    assert con.execute("SELECT count(*) FROM chunks").fetchone()[0] == 1


def test_index_file_semantic_reindexes_changed_content(tmp_path):
    con = _open(tmp_path)
    f = tmp_path / "note.txt"
    f.write_text("original content")
    index_file_semantic(con, f, FakeEmbedder())
    con.commit()

    f.write_text("updated content here")
    changed = index_file_semantic(con, f, FakeEmbedder())
    con.commit()

    assert changed is True
    row = con.execute("SELECT text FROM chunks WHERE path = ?", (str(f),)).fetchone()
    assert row[0] == "updated content here"


def test_remove_chunks_deletes_rows_and_vectors(tmp_path):
    con = _open(tmp_path)
    f = tmp_path / "note.txt"
    f.write_text("to be removed")
    index_file_semantic(con, f, FakeEmbedder())
    con.commit()

    removed = remove_chunks(con, f)
    con.commit()

    assert removed == 1
    assert con.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM chunk_vectors").fetchone()[0] == 0


def test_index_roots_semantic_indexes_every_matching_file(tmp_path):
    con = _open(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    (root / "a.txt").write_text("alpha content")
    (root / "b.md").write_text("beta content")

    count = index_roots_semantic(con, [root], FakeEmbedder())

    assert count == 2
    paths = {row[0] for row in con.execute("SELECT DISTINCT path FROM chunks").fetchall()}
    assert paths == {str(root / "a.txt"), str(root / "b.md")}


def test_reconcile_roots_semantic_removes_chunks_for_deleted_files(tmp_path):
    con = _open(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    keep = root / "keep.txt"
    gone = root / "gone.txt"
    keep.write_text("keep me")
    gone.write_text("delete me")
    index_roots_semantic(con, [root], FakeEmbedder())

    gone.unlink()
    result = reconcile_roots_semantic(con, [root], FakeEmbedder())

    assert result.removed == 1
    paths = {row[0] for row in con.execute("SELECT DISTINCT path FROM chunks").fetchall()}
    assert paths == {str(keep)}


def test_semantic_search_ranks_shared_vocabulary_higher(tmp_path):
    con = _open(tmp_path)
    embedder = FakeEmbedder()
    related = tmp_path / "related.txt"
    unrelated = tmp_path / "unrelated.txt"
    related.write_text("budget meeting quarterly plan review")
    unrelated.write_text("lunch kimchi stew recipe today")
    index_file_semantic(con, related, embedder)
    index_file_semantic(con, unrelated, embedder)
    con.commit()

    results = semantic_search(con, "quarterly budget review", embedder, limit=2)

    assert results[0].path == str(related)
    assert results[0].score > results[1].score


def test_semantic_search_respects_limit(tmp_path):
    con = _open(tmp_path)
    embedder = FakeEmbedder()
    for i in range(5):
        f = tmp_path / f"note{i}.txt"
        f.write_text("repeated keyword content")
        index_file_semantic(con, f, embedder)
    con.commit()

    results = semantic_search(con, "keyword", embedder, limit=2)

    assert len(results) == 2
