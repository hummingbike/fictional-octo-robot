import json

from sbsearch.cli import main


def _config_path(tmp_path):
    return str(tmp_path / "config.json")


def test_root_add_list_remove(tmp_path, capsys):
    config_path = _config_path(tmp_path)
    folder = tmp_path / "notes"
    folder.mkdir()

    assert main(["--config", config_path, "root", "add", str(folder)]) == 0
    capsys.readouterr()

    main(["--config", config_path, "root", "list"])
    listed = capsys.readouterr().out.strip()
    assert listed == str(folder.resolve())

    main(["--config", config_path, "root", "remove", str(folder)])
    capsys.readouterr()
    main(["--config", config_path, "root", "list"])
    assert capsys.readouterr().out.strip() == ""


def test_exclude_add_list_remove(tmp_path, capsys):
    config_path = _config_path(tmp_path)

    main(["--config", config_path, "exclude", "add", "drafts/"])
    capsys.readouterr()

    main(["--config", config_path, "exclude", "list"])
    assert capsys.readouterr().out.strip() == "drafts/"

    main(["--config", config_path, "exclude", "remove", "drafts/"])
    capsys.readouterr()
    main(["--config", config_path, "exclude", "list"])
    assert capsys.readouterr().out.strip() == ""


def test_index_then_search_plain_output(tmp_path, capsys):
    config_path = _config_path(tmp_path)
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "alpha.txt").write_text("the quick brown fox")
    (folder / "beta.txt").write_text("completely unrelated content")

    main(["--config", config_path, "root", "add", str(folder)])
    capsys.readouterr()

    main(["--config", config_path, "index"])
    index_output = capsys.readouterr().out
    assert "indexed 2 files" in index_output

    main(["--config", config_path, "search", "fox"])
    search_output = capsys.readouterr().out
    assert "alpha.txt" in search_output
    assert "beta.txt" not in search_output


def test_index_respects_exclude_patterns(tmp_path, capsys):
    config_path = _config_path(tmp_path)
    folder = tmp_path / "notes"
    folder.mkdir()
    drafts = folder / "drafts"
    drafts.mkdir()
    (folder / "keep.txt").write_text("keep me")
    (drafts / "wip.txt").write_text("work in progress")

    main(["--config", config_path, "root", "add", str(folder)])
    capsys.readouterr()
    main(["--config", config_path, "exclude", "add", "drafts/"])
    capsys.readouterr()

    main(["--config", config_path, "index"])
    output = capsys.readouterr().out
    assert "indexed 1 files" in output


def test_search_json_output(tmp_path, capsys):
    config_path = _config_path(tmp_path)
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "alpha.txt").write_text("the quick brown fox")

    main(["--config", config_path, "root", "add", str(folder)])
    capsys.readouterr()
    main(["--config", config_path, "index"])
    capsys.readouterr()

    main(["--config", config_path, "search", "fox", "--json"])
    output = capsys.readouterr().out
    results = json.loads(output)

    assert len(results) == 1
    assert results[0]["path"].endswith("alpha.txt")


def test_search_limit_option(tmp_path, capsys):
    config_path = _config_path(tmp_path)
    folder = tmp_path / "notes"
    folder.mkdir()
    for i in range(5):
        (folder / f"note{i}.txt").write_text("needle")

    main(["--config", config_path, "root", "add", str(folder)])
    capsys.readouterr()
    main(["--config", config_path, "index"])
    capsys.readouterr()

    main(["--config", config_path, "search", "needle", "--limit", "2", "--json"])
    results = json.loads(capsys.readouterr().out)

    assert len(results) == 2


def test_status_reports_file_count(tmp_path, capsys):
    config_path = _config_path(tmp_path)
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "alpha.txt").write_text("hello")

    main(["--config", config_path, "root", "add", str(folder)])
    capsys.readouterr()
    main(["--config", config_path, "index"])
    capsys.readouterr()

    main(["--config", config_path, "status"])
    status = json.loads(capsys.readouterr().out)

    assert status["file_count"] == 1
    assert status["last_indexed"] is not None
    assert status["db_size_bytes"] > 0
