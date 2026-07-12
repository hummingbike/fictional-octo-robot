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


def test_search_bare_korean_term_matches_inflected_token(tmp_path):
    con = _indexed(
        tmp_path,
        {
            "meeting.md": "오늘 회의에서 예산안을 논의했다",
            "unrelated.md": "장보기 목록: 우유, 계란",
        },
    )

    for query in ("예산안", "회의", "예산안 논의"):
        results = search(con, query)
        assert [r.path.endswith("meeting.md") for r in results] == [True], query


def test_search_plain_multi_term_query_requires_all_terms(tmp_path):
    con = _indexed(
        tmp_path,
        {
            "both.txt": "quick brown fox",
            "one.txt": "quick rabbit",
        },
    )

    results = search(con, "quick fox")

    assert [r.path.endswith("both.txt") for r in results] == [True]


def test_search_plain_query_with_punctuation_does_not_raise(tmp_path):
    con = _indexed(tmp_path, {"note.txt": "check the foo-bar setting"})

    results = search(con, "foo-bar")

    assert [r.path.endswith("note.txt") for r in results] == [True]


def test_search_query_with_fts5_syntax_is_passed_through(tmp_path):
    con = _indexed(
        tmp_path,
        {
            "exact.txt": "예산안 확정",
            "inflected.txt": "예산안을 논의했다",
        },
    )

    results = search(con, '"예산안" 확정')

    assert [r.path.endswith("exact.txt") for r in results] == [True]


def test_search_snippet_highlights_match(tmp_path):
    con = _indexed(tmp_path, {"alpha.txt": "the quick brown fox jumps"})

    results = search(con, "fox")

    assert ">>>fox<<<" in results[0].snippet


def test_search_context_tokens_limits_snippet_width(tmp_path):
    con = _indexed(
        tmp_path,
        {"alpha.txt": "one two three four needle six seven eight nine ten"},
    )

    narrow = search(con, "needle", context_tokens=1)[0].snippet
    wide = search(con, "needle", context_tokens=10)[0].snippet

    assert len(narrow) < len(wide)
    assert ">>>needle<<<" in narrow
    assert ">>>needle<<<" in wide
