import json
import threading
import time

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


def test_index_removes_entries_for_deleted_files(tmp_path, capsys):
    config_path = _config_path(tmp_path)
    folder = tmp_path / "notes"
    folder.mkdir()
    keep = folder / "keep.txt"
    gone = folder / "gone.txt"
    keep.write_text("keep me")
    gone.write_text("delete me")

    main(["--config", config_path, "root", "add", str(folder)])
    capsys.readouterr()
    main(["--config", config_path, "index"])
    first_output = capsys.readouterr().out
    assert "indexed 2 files" in first_output

    gone.unlink()
    main(["--config", config_path, "index"])
    second_output = capsys.readouterr().out
    assert "indexed 1 files" in second_output  # keep.txt still walked/processed
    assert "removed 1 stale entries" in second_output  # gone.txt's stale entry dropped

    main(["--config", config_path, "status"])
    status = json.loads(capsys.readouterr().out)
    assert status["file_count"] == 1


def test_watch_with_timeout_indexes_newly_created_file(tmp_path, capsys):
    config_path = _config_path(tmp_path)
    folder = tmp_path / "notes"
    folder.mkdir()

    main(["--config", config_path, "root", "add", str(folder)])
    capsys.readouterr()

    def write_after_delay():
        time.sleep(0.3)
        (folder / "new.txt").write_text("hello fox")

    writer = threading.Thread(target=write_after_delay)
    writer.start()
    main(["--config", config_path, "watch", "--timeout", "2.0"])
    writer.join()
    capsys.readouterr()

    main(["--config", config_path, "search", "fox", "--json"])
    results = json.loads(capsys.readouterr().out)
    assert len(results) == 1
    assert results[0]["path"].endswith("new.txt")


def test_watch_without_roots_returns_error(tmp_path, capsys):
    config_path = _config_path(tmp_path)

    exit_code = main(["--config", config_path, "watch", "--timeout", "0.1"])

    assert exit_code == 1
    assert "no roots registered" in capsys.readouterr().out


def test_index_semantic_then_search_semantic(tmp_path, capsys):
    config_path = _config_path(tmp_path)
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "budget.txt").write_text("이번 분기 예산 계획을 검토했다")
    (folder / "lunch.txt").write_text("점심으로 김치찌개를 먹었다")

    main(["--config", config_path, "root", "add", str(folder)])
    capsys.readouterr()

    main(["--config", config_path, "index", "--semantic"])
    index_output = capsys.readouterr().out
    assert "semantic: indexed 2 files" in index_output

    main(["--config", config_path, "search", "오늘 회의에서 예산안을 논의했다", "--semantic", "--json"])
    results = json.loads(capsys.readouterr().out)

    assert results[0]["path"].endswith("budget.txt")


def test_search_semantic_with_no_semantic_index_returns_empty(tmp_path, capsys):
    config_path = _config_path(tmp_path)
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "a.txt").write_text("some note content")
    main(["--config", config_path, "root", "add", str(folder)])
    capsys.readouterr()
    main(["--config", config_path, "index"])  # keyword-only, no --semantic
    capsys.readouterr()

    main(["--config", config_path, "search", "anything", "--semantic", "--json"])
    results = json.loads(capsys.readouterr().out)

    assert results == []


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
