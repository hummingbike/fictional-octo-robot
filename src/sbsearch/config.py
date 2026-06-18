"""Folder registration and exclude-pattern persistence (F1).

A `Config` lists the root folders to index and a set of .gitignore-style
exclude patterns (see `sbsearch.excludes`). It is persisted as JSON next to
wherever the CLI is told to look (default: ~/.sbsearch/config.json).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".sbsearch" / "config.json"


@dataclass
class Config:
    roots: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    db_path: str | None = None  # None => sibling "index.db" next to the config file


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> Config:
    """Load config from `path`, or return defaults if it doesn't exist yet."""
    path = Path(path)
    if not path.exists():
        return Config()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Config(
        roots=data.get("roots", []),
        exclude_patterns=data.get("exclude_patterns", []),
        db_path=data.get("db_path"),
    )


def save_config(config: Config, path: Path | str = DEFAULT_CONFIG_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")


def resolve_db_path(config: Config, config_path: Path | str = DEFAULT_CONFIG_PATH) -> Path:
    """Resolve the index db location: explicit `config.db_path`, else a sibling of the config file."""
    if config.db_path:
        return Path(config.db_path)
    return Path(config_path).parent / "index.db"


def add_root(config: Config, root: Path | str) -> Config:
    resolved = str(Path(root).resolve())
    if resolved not in config.roots:
        config.roots.append(resolved)
    return config


def remove_root(config: Config, root: Path | str) -> Config:
    resolved = str(Path(root).resolve())
    config.roots = [r for r in config.roots if r != resolved]
    return config


def add_exclude(config: Config, pattern: str) -> Config:
    if pattern not in config.exclude_patterns:
        config.exclude_patterns.append(pattern)
    return config


def remove_exclude(config: Config, pattern: str) -> Config:
    config.exclude_patterns = [p for p in config.exclude_patterns if p != pattern]
    return config
