"""Real-time incremental indexing via filesystem events (F3, Phase 2).

Subscribes to filesystem change notifications (FSEvents on macOS, via the
`watchdog` library) for each registered root and keeps the FTS5 index in
sync without a full re-scan -- PLAN.md's "증분 갱신은 파일 단위로 국소화"
principle: one event = one file re-indexed, never a full re-walk.

Multiple rapid events on the same path (e.g. an editor's write-then-rename
save) are debounced into a single re-index/remove.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from sbsearch.excludes import build_pathspec, is_excluded
from sbsearch.indexer import DEFAULT_EXTENSIONS, index_file, remove_file

DEFAULT_DEBOUNCE_SECONDS = 0.3


class Debouncer:
    """Coalesces repeated calls for the same key into one delayed action."""

    def __init__(self, delay: float = DEFAULT_DEBOUNCE_SECONDS) -> None:
        self._delay = delay
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def schedule(self, key: str, action: Callable[[], None]) -> None:
        with self._lock:
            existing = self._timers.get(key)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(self._delay, self._fire, args=(key, action))
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

    def _fire(self, key: str, action: Callable[[], None]) -> None:
        action()
        with self._lock:
            self._timers.pop(key, None)

    def wait_idle(self, timeout: float = 5.0) -> None:
        """Block until no debounce timers are pending. Used by tests/CLI shutdown."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if not self._timers:
                    return
            time.sleep(0.01)


class _RootEventHandler(FileSystemEventHandler):
    """Routes filesystem events for one watched root into debounced index updates."""

    def __init__(
        self,
        con: sqlite3.Connection,
        write_lock: threading.Lock,
        root: Path,
        extensions: tuple[str, ...],
        exclude_spec,
        debouncer: Debouncer,
    ) -> None:
        self._con = con
        self._write_lock = write_lock
        self._root = root
        self._extensions = extensions
        self._exclude_spec = exclude_spec
        self._debouncer = debouncer

    def _is_relevant(self, path: Path) -> bool:
        if path.suffix not in self._extensions:
            return False
        if self._exclude_spec is not None and is_excluded(self._exclude_spec, self._root, path):
            return False
        return True

    def _schedule_upsert(self, path_str: str) -> None:
        path = Path(path_str)
        if not self._is_relevant(path):
            return

        def action() -> None:
            with self._write_lock:
                if path.exists():
                    index_file(self._con, path)
                    self._con.commit()

        self._debouncer.schedule(path_str, action)

    def _schedule_remove(self, path_str: str) -> None:
        path = Path(path_str)
        if not self._is_relevant(path):
            return

        def action() -> None:
            with self._write_lock:
                remove_file(self._con, path_str)
                self._con.commit()

        self._debouncer.schedule(path_str, action)

    def on_created(self, event) -> None:
        if not event.is_directory:
            self._schedule_upsert(event.src_path)

    def on_modified(self, event) -> None:
        if not event.is_directory:
            self._schedule_upsert(event.src_path)

    def on_deleted(self, event) -> None:
        if not event.is_directory:
            self._schedule_remove(event.src_path)

    def on_moved(self, event) -> None:
        if not event.is_directory:
            self._schedule_remove(event.src_path)
            self._schedule_upsert(event.dest_path)


class IndexWatcher:
    """Watches registered roots and keeps the FTS5 index in sync (F3).

    `con` must be opened with `open_index(db_path, check_same_thread=False)`,
    since debounced re-index actions run on timer threads.
    """

    def __init__(
        self,
        con: sqlite3.Connection,
        roots: Iterable[Path | str],
        extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
        exclude_patterns: tuple[str, ...] | list[str] | None = None,
        debounce_seconds: float = DEFAULT_DEBOUNCE_SECONDS,
    ) -> None:
        self._write_lock = threading.Lock()
        self._debouncer = Debouncer(debounce_seconds)
        self._observer = Observer()
        spec = build_pathspec(exclude_patterns) if exclude_patterns else None

        for root in roots:
            # Resolve before scheduling: FSEvents silently drops events for
            # unresolved symlinked paths (see BENCHMARK_EVERYTHING.md sec. 5).
            resolved_root = Path(root).resolve()
            handler = _RootEventHandler(
                con, self._write_lock, resolved_root, extensions, spec, self._debouncer
            )
            self._observer.schedule(handler, str(resolved_root), recursive=True)

    def start(self) -> None:
        self._observer.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._observer.stop()
        self._observer.join(timeout=timeout)

    def wait_idle(self, timeout: float = 5.0) -> None:
        """Block until pending debounced updates have been applied."""
        self._debouncer.wait_idle(timeout)
