"""Benchmark/spike: measure file-system change notification latency.

On macOS this exercises FSEvents via the `watchdog` library -- our
equivalent of Everything's USN Journal subscription (see
BENCHMARK_EVERYTHING.md section 2). Measures how long after a file write
the observer's callback actually fires, and whether any events are
dropped under a burst of rapid writes.
"""

from __future__ import annotations

import queue
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


@dataclass
class LatencyResult:
    samples: list[float]  # seconds from write to event delivery, one per file
    dropped: int  # files whose event never arrived within the timeout

    @property
    def mean(self) -> float:
        return statistics.mean(self.samples) if self.samples else float("nan")

    @property
    def max(self) -> float:
        return max(self.samples) if self.samples else float("nan")


class _QueueHandler(FileSystemEventHandler):
    def __init__(self, event_queue: "queue.Queue[tuple[str, float]]") -> None:
        self._queue = event_queue

    def _push(self, event) -> None:
        if not event.is_directory:
            self._queue.put((event.src_path, time.perf_counter()))

    def on_created(self, event) -> None:
        self._push(event)

    def on_modified(self, event) -> None:
        self._push(event)


def measure_create_latency(
    root: Path, num_files: int = 20, timeout: float = 5.0
) -> LatencyResult:
    """Write `num_files` files one at a time, measuring delivery latency for each.

    A file write can trigger both a create and a modify event; we take the
    first event matching the file we just wrote and discard the rest, so
    duplicate notifications don't get misattributed to the next file.

    `root` is resolved (symlinks followed) before watching: on macOS,
    watching an unresolved path such as `/var/...` (a symlink to
    `/private/var/...`, which is what `tempfile.mkdtemp()` returns) makes
    FSEvents silently deliver zero events -- every write times out. This
    cost real debugging time during the Phase 0 spike (see
    BENCHMARK_EVERYTHING.md section 5), so the fix lives here rather than
    being left to every caller to know about.
    """
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    event_queue: "queue.Queue[tuple[str, float]]" = queue.Queue()
    observer = Observer()
    observer.schedule(_QueueHandler(event_queue), str(root), recursive=False)
    observer.start()

    samples: list[float] = []
    dropped = 0
    try:
        for i in range(num_files):
            target = root / f"watch_{i:04d}.txt"
            start = time.perf_counter()
            target.write_text("content")

            deadline = start + timeout
            matched = False
            while not matched:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    dropped += 1
                    break
                try:
                    path, received_at = event_queue.get(timeout=remaining)
                except queue.Empty:
                    dropped += 1
                    break
                if path == str(target):
                    samples.append(received_at - start)
                    matched = True
    finally:
        observer.stop()
        observer.join(timeout=5)

    return LatencyResult(samples=samples, dropped=dropped)
