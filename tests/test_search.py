from sbsearch.indexer import index_file, open_index
from sbsearch.search import search


def _indexed(tmp_path, files: dict[str, str]):
    con = open_index(tmp_path / "index.db")
    for name, content in files.items():
        path = tmp_path / name
        path.write_text(content)
        index_file(con, path)
    con.commit()
    return con


def test_search_finds_file_containing_keyword(tmp_path):
    con = _indexed(
        tmp_path,
        {
            "alpha.txt": "the quick brown fox",
            "beta.txt": "completely unrelated content",
        },
    )

    results = search(con, "fox")

    assert [r.path.endswith("alpha.txt") for r in results] == [True]


def test_search_returns_no_results_for_absent_term(tmp_path):
    con = _indexed(tmp_path, {"alpha.txt": "the quick brown fox"})

    assert search(con, "nonexistentterm") == []


def test_search_ranks_more_relevant_file_first(tmp_path):
    con = _indexed(
        tmp_path,
        {
            "sparse.txt": "needle appears once here",
            "dense.txt": "needle needle needle needle everywhere",
        },
    )

    results = search(con, "needle")

    assert len(results) == 2
    assert results[0].path.endswith("dense.txt")


def test_search_supports_phrase_query(tmp_path):
    con = _indexed(
        tmp_path,
        {
            "match.txt": "second brain knowledge base",
            "nomatch.txt": "brain storming about knowledge",
        },
    )

    results = search(con, '"second brain"')

    assert len(results) == 1
    assert results[0].path.endswith("match.txt")


def test_search_supports_not_operator(tmp_path):
    con = _indexed(
        tmp_path,
        {
            "keep.txt": "apple orange",
            "drop.txt": "apple banana",
        },
    )

    results = search(con, "apple NOT banana")

    assert len(results) == 1
    assert results[0].path.endswith("keep.txt")


def test_search_snippet_highlights_match(tmp_path):
    con = _indexed(tmp_path, {"alpha.txt": "the quick brown fox jumps"})

    results = search(con, "fox")

    assert ">>>fox<<<" in results[0].snippet
