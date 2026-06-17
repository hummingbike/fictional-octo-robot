"""Synthetic text corpus generator used to benchmark indexing/search.

Produces a deterministic (seeded) set of txt/md/log files with random
filler words, optionally seeding a known "needle" phrase into a subset
of files so benchmark/test code can assert exact recall.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

_VOCAB = [
    "apple", "banner", "cascade", "delta", "ember", "falcon", "glacier",
    "harbor", "ivory", "jungle", "kernel", "lantern", "meadow", "nebula",
    "oracle", "pebble", "quartz", "ridge", "summit", "thicket", "umbra",
    "velvet", "willow", "xenon", "yonder", "zephyr", "amber", "birch",
    "cobalt", "drift",
]


@dataclass
class Corpus:
    root: Path
    paths: list[Path]
    needle_paths: list[Path]


def generate_corpus(
    root: Path,
    num_files: int,
    *,
    min_words: int = 50,
    max_words: int = 300,
    extensions: tuple[str, ...] = (".txt", ".md", ".log"),
    seed: int = 0,
    needle: str | None = None,
    needle_file_count: int = 0,
    files_per_dir: int = 200,
) -> Corpus:
    """Write `num_files` synthetic documents under `root`.

    Files are distributed across numbered subdirectories (`files_per_dir`
    each) to mimic a real multi-folder note vault rather than one flat
    directory. Returns the paths written and, if `needle` was given, which
    of those paths contain it (for recall assertions in tests/benchmarks).
    """
    rng = random.Random(seed)
    root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    needle_paths: list[Path] = []

    for i in range(num_files):
        subdir = root / f"folder_{i // files_per_dir:04d}"
        subdir.mkdir(parents=True, exist_ok=True)
        ext = extensions[i % len(extensions)]
        file_path = subdir / f"note_{i:06d}{ext}"

        word_count = rng.randint(min_words, max_words)
        words = [rng.choice(_VOCAB) for _ in range(word_count)]

        plant_needle = needle is not None and i < needle_file_count
        if plant_needle:
            insert_at = rng.randint(0, len(words))
            words[insert_at:insert_at] = needle.split()

        text = " ".join(words)
        file_path.write_text(text, encoding="utf-8")

        paths.append(file_path)
        if plant_needle:
            needle_paths.append(file_path)

    return Corpus(root=root, paths=paths, needle_paths=needle_paths)
