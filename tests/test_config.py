from pathlib import Path

from sbsearch.config import (
    Config,
    add_exclude,
    add_root,
    load_config,
    remove_exclude,
    remove_root,
    resolve_db_path,
    save_config,
)


def test_load_config_returns_defaults_when_missing(tmp_path):
    config = load_config(tmp_path / "missing.json")

    assert config == Config()


def test_add_root_resolves_and_dedupes(tmp_path):
    folder = tmp_path / "notes"
    folder.mkdir()
    config = Config()

    add_root(config, folder)
    add_root(config, folder)  # duplicate add is a no-op

    assert config.roots == [str(folder.resolve())]


def test_remove_root_drops_matching_entry(tmp_path):
    folder = tmp_path / "notes"
    folder.mkdir()
    config = Config()
    add_root(config, folder)

    remove_root(config, folder)

    assert config.roots == []


def test_add_and_remove_exclude_pattern():
    config = Config()

    add_exclude(config, "*.log")
    add_exclude(config, "*.log")  # duplicate add is a no-op
    assert config.exclude_patterns == ["*.log"]

    remove_exclude(config, "*.log")
    assert config.exclude_patterns == []


def test_save_and_load_config_roundtrip(tmp_path):
    config_path = tmp_path / "config.json"
    folder = tmp_path / "notes"
    folder.mkdir()
    config = Config()
    add_root(config, folder)
    add_exclude(config, "drafts/")

    save_config(config, config_path)
    loaded = load_config(config_path)

    assert loaded == config


def test_resolve_db_path_defaults_to_config_sibling(tmp_path):
    config_path = tmp_path / "sub" / "config.json"
    config = Config()

    assert resolve_db_path(config, config_path) == config_path.parent / "index.db"


def test_resolve_db_path_uses_explicit_override(tmp_path):
    config = Config(db_path=str(tmp_path / "custom.db"))

    assert resolve_db_path(config, tmp_path / "config.json") == Path(tmp_path / "custom.db")
