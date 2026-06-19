import shutil

import pytest

from sbsearch.bench.fts5_vs_ripgrep import run_benchmark

RG_PATH = shutil.which("rg")


@pytest.mark.skipif(RG_PATH is None, reason="ripgrep not installed")
def test_benchmark_returns_consistent_match_counts(tmp_path):
    result = run_benchmark(
        num_files=30,
        needle_file_count=4,
        repeats=2,
        rg_path=RG_PATH,
        workdir=tmp_path,
    )

    assert result.num_files == 30
    assert result.fts5_found_count == 4
    assert result.ripgrep_found_count == 4
    assert result.index_build_seconds >= 0
    assert result.fts5_search_seconds >= 0
    assert result.ripgrep_search_seconds >= 0


@pytest.mark.skipif(RG_PATH is None, reason="ripgrep not installed")
def test_search_speedup_meets_prd_m1_target(tmp_path):
    # PRD.md M1: FTS5 search must beat a ripgrep full rescan by >= 5x.
    # Phase 0 measured ~2,650x at 10k files; even this small corpus measures
    # 100x+ locally, so 5x leaves a wide margin against CI noise while still
    # catching the realistic regression (a search path that re-scans disk).
    result = run_benchmark(
        num_files=200,
        needle_file_count=3,
        repeats=3,
        rg_path=RG_PATH,
        workdir=tmp_path,
    )

    assert result.speedup >= 5
