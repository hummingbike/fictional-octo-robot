"""Index status reporting (F8): file count, last update time, index size."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

_SIDECAR_SUFFIXES = ("-wal", "-shm")


@dataclass
class IndexStatus:
    file_count: int
    last_indexed: float | None  # max mtime (epoch seconds) among indexed files
    db_size_bytes: int


def get_status(con: sqlite3.Connection, db_path: Path | str) -> IndexStatus:
    file_count, last_indexed = con.execute(
        "SELECT count(*), max(mtime) FROM files_fts"
    ).fetchone()

    path = Path(db_path)
    db_size_bytes = path.stat().st_size if path.exists() else 0
    for suffix in _SIDECAR_SUFFIXES:
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists():
            db_size_bytes += sidecar.stat().st_size

    return IndexStatus(
        file_count=file_count,
        last_indexed=last_indexed,
        db_size_bytes=db_size_bytes,
    )
