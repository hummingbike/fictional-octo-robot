import tempfile
from pathlib import Path

from sbsearch.bench.watch_latency import measure_create_latency


def test_measure_create_latency_detects_all_file_creations(tmp_path):
    result = measure_create_latency(tmp_path, num_files=5, timeout=5.0)

    assert result.dropped == 0
    assert len(result.samples) == 5
    assert all(sample >= 0 for sample in result.samples)
    assert result.max < 5.0


def test_measure_create_latency_handles_unresolved_symlinked_tmpdir():
    # On macOS, tempfile.mkdtemp() returns a path through the /var -> /private/var
    # symlink. Watching that unresolved path makes FSEvents silently deliver zero
    # events (see BENCHMARK_EVERYTHING.md section 5) -- this is a regression test
    # for the .resolve() fix in measure_create_latency.
    with tempfile.TemporaryDirectory() as raw_dir:
        result = measure_create_latency(Path(raw_dir), num_files=5, timeout=5.0)

    assert result.dropped == 0
    assert len(result.samples) == 5
