"""Benchmark: FTS5 indexed search vs. ripgrep full-rescan, on the same corpus.

Validates the core design principle from BENCHMARK_EVERYTHING.md: once a
file is indexed, search should be index-lookup-only and should beat a
full-corpus rescan tool (ripgrep) by a wide and growing margin as corpus
size increases. Run directly for a human-readable report:

    python -m sbsearch.bench.fts5_vs_ripgrep --num-files 10000
"""

from __future__ import annotations

import argparse
import shutil
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from sbsearch.bench.corpus import generate_corpus
from sbsearch.indexer import index_directory, open_index
from sbsearch.search import search

NEEDLE = "zzzneedletoken"


@dataclass
class BenchmarkResult:
    num_files: int
    corpus_bytes: int
    index_build_seconds: float
    fts5_search_seconds: float  # average per query, warm index
    ripgrep_search_seconds: float  # average per invocation
    needle_file_count: int
    fts5_found_count: int
    ripgrep_found_count: int
    speedup: float  # ripgrep_search_seconds / fts5_search_seconds


def run_benchmark(
    num_files: int = 2000,
    needle_file_count: int = 5,
    repeats: int = 5,
    seed: int = 0,
    rg_path: str = "rg",
    workdir: Path | None = None,
) -> BenchmarkResult:
    cleanup = workdir is None
    workdir = workdir or Path(tempfile.mkdtemp(prefix="sbsearch-bench-"))
    try:
        corpus_root = workdir / "corpus"
        corpus = generate_corpus(
            corpus_root,
            num_files=num_files,
            seed=seed,
            needle=NEEDLE,
            needle_file_count=needle_file_count,
        )
        corpus_bytes = sum(p.stat().st_size for p in corpus.paths)

        db_path = workdir / "index.db"
        con = open_index(db_path)
        start = time.perf_counter()
        index_directory(con, corpus_root)
        index_build_seconds = time.perf_counter() - start

        fts5_times = []
        fts5_found = []
        for _ in range(repeats):
            start = time.perf_counter()
            results = search(con, NEEDLE, limit=num_files)
            fts5_times.append(time.perf_counter() - start)
            fts5_found.append(len(results))

        rg_times = []
        rg_found = []
        for _ in range(repeats):
            start = time.perf_counter()
            proc = subprocess.run(
                [rg_path, "-l", NEEDLE, str(corpus_root)],
                capture_output=True,
                text=True,
            )
            rg_times.append(time.perf_counter() - start)
            rg_found.append(len(proc.stdout.strip().splitlines()))

        fts5_avg = statistics.mean(fts5_times)
        rg_avg = statistics.mean(rg_times)

        return BenchmarkResult(
            num_files=num_files,
            corpus_bytes=corpus_bytes,
            index_build_seconds=index_build_seconds,
            fts5_search_seconds=fts5_avg,
            ripgrep_search_seconds=rg_avg,
            needle_file_count=needle_file_count,
            fts5_found_count=fts5_found[0],
            ripgrep_found_count=rg_found[0],
            speedup=rg_avg / fts5_avg if fts5_avg > 0 else float("inf"),
        )
    finally:
        if cleanup:
            shutil.rmtree(workdir, ignore_errors=True)


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-files", type=int, default=2000)
    parser.add_argument("--needle-file-count", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--rg-path", default="rg")
    args = parser.parse_args()

    result = run_benchmark(
        num_files=args.num_files,
        needle_file_count=args.needle_file_count,
        repeats=args.repeats,
        rg_path=args.rg_path,
    )

    print(f"corpus:            {result.num_files} files, {result.corpus_bytes / 1e6:.1f} MB")
    print(f"index build:       {result.index_build_seconds:.3f} s")
    print(f"fts5 search (avg): {result.fts5_search_seconds * 1000:.2f} ms  -> {result.fts5_found_count} matches")
    print(f"ripgrep (avg):     {result.ripgrep_search_seconds * 1000:.2f} ms  -> {result.ripgrep_found_count} matches")
    print(f"speedup:           {result.speedup:.1f}x")


if __name__ == "__main__":
    _main()
