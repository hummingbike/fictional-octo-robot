from sbsearch.bench.corpus import generate_corpus


def test_generate_corpus_creates_expected_file_count(tmp_path):
    corpus = generate_corpus(tmp_path, num_files=25, files_per_dir=10)

    assert len(corpus.paths) == 25
    assert all(p.exists() for p in corpus.paths)


def test_generate_corpus_spreads_across_subdirectories(tmp_path):
    corpus = generate_corpus(tmp_path, num_files=25, files_per_dir=10)

    subdirs = {p.parent for p in corpus.paths}
    assert len(subdirs) == 3  # 25 files / 10 per dir -> folders 0,1,2


def test_generate_corpus_uses_requested_extensions(tmp_path):
    corpus = generate_corpus(tmp_path, num_files=9, extensions=(".txt", ".md", ".log"))

    suffixes = {p.suffix for p in corpus.paths}
    assert suffixes == {".txt", ".md", ".log"}


def test_generate_corpus_is_deterministic_for_same_seed(tmp_path):
    a = generate_corpus(tmp_path / "a", num_files=10, seed=42)
    b = generate_corpus(tmp_path / "b", num_files=10, seed=42)

    contents_a = [p.read_text() for p in a.paths]
    contents_b = [p.read_text() for p in b.paths]
    assert contents_a == contents_b


def test_generate_corpus_plants_needle_in_requested_files(tmp_path):
    corpus = generate_corpus(
        tmp_path, num_files=20, needle="unique-search-phrase", needle_file_count=5
    )

    assert len(corpus.needle_paths) == 5
    for path in corpus.needle_paths:
        assert "unique-search-phrase" in path.read_text()

    non_needle_paths = set(corpus.paths) - set(corpus.needle_paths)
    for path in non_needle_paths:
        assert "unique-search-phrase" not in path.read_text()
