from sbsearch.excludes import build_pathspec, is_excluded


def test_simple_glob_pattern_excludes_matching_file(tmp_path):
    spec = build_pathspec(["*.log"])

    assert is_excluded(spec, tmp_path, tmp_path / "a.log") is True
    assert is_excluded(spec, tmp_path, tmp_path / "a.txt") is False


def test_directory_pattern_excludes_nested_files(tmp_path):
    spec = build_pathspec(["drafts/"])

    assert is_excluded(spec, tmp_path, tmp_path / "drafts" / "note.md") is True
    assert is_excluded(spec, tmp_path, tmp_path / "final" / "note.md") is False


def test_empty_pattern_list_excludes_nothing(tmp_path):
    spec = build_pathspec([])

    assert is_excluded(spec, tmp_path, tmp_path / "anything.txt") is False


def test_negation_pattern_reincludes_file(tmp_path):
    spec = build_pathspec(["*.log", "!keep.log"])

    assert is_excluded(spec, tmp_path, tmp_path / "drop.log") is True
    assert is_excluded(spec, tmp_path, tmp_path / "keep.log") is False
