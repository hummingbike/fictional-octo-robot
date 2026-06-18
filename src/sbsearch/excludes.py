"""gitignore-style exclude pattern matching, shared by config and indexer (F1)."""

from __future__ import annotations

from pathlib import Path

import pathspec


def build_pathspec(patterns: list[str] | tuple[str, ...]) -> pathspec.PathSpec:
    """Compile exclude patterns using git's wildmatch (.gitignore) syntax."""
    return pathspec.PathSpec.from_lines("gitignore", patterns)


def is_excluded(spec: pathspec.PathSpec, root: Path, path: Path) -> bool:
    """Check whether `path` (under `root`) matches the exclude spec."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return spec.match_file(str(rel))
