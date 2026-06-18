"""sbsearch CLI: folder registration, indexing, search, status, semantic mode (F1, F4, F6, F7, F8)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from sbsearch.config import (
    DEFAULT_CONFIG_PATH,
    add_exclude,
    add_root,
    load_config,
    remove_exclude,
    remove_root,
    resolve_db_path,
    save_config,
)
from sbsearch.indexer import open_index, reconcile_roots
from sbsearch.search import DEFAULT_CONTEXT_TOKENS, search
from sbsearch.status import get_status
from sbsearch.watcher import DEFAULT_DEBOUNCE_SECONDS, IndexWatcher


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sbsearch", description="개빠름 메모검색")
    parser.add_argument(
        "--config", default=str(DEFAULT_CONFIG_PATH), help="config file path"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    root_p = sub.add_parser("root", help="manage registered root folders (F1)")
    root_sub = root_p.add_subparsers(dest="root_command", required=True)
    root_add = root_sub.add_parser("add", help="register a folder to index")
    root_add.add_argument("path")
    root_remove = root_sub.add_parser("remove", help="unregister a folder")
    root_remove.add_argument("path")
    root_sub.add_parser("list", help="list registered folders")

    exclude_p = sub.add_parser("exclude", help="manage .gitignore-style exclude patterns (F1)")
    exclude_sub = exclude_p.add_subparsers(dest="exclude_command", required=True)
    exclude_add = exclude_sub.add_parser("add", help="add an exclude pattern")
    exclude_add.add_argument("pattern")
    exclude_remove = exclude_sub.add_parser("remove", help="remove an exclude pattern")
    exclude_remove.add_argument("pattern")
    exclude_sub.add_parser("list", help="list exclude patterns")

    index_p = sub.add_parser(
        "index", help="build/refresh the full-text index from registered roots (F2)"
    )
    index_p.add_argument(
        "--semantic",
        action="store_true",
        dest="as_semantic",
        help="also build/refresh the semantic (embedding) index (F6)",
    )

    watch_p = sub.add_parser(
        "watch", help="watch registered roots and keep the index in sync (F3)"
    )
    watch_p.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="stop after N seconds (omit to run until Ctrl+C)",
    )

    search_p = sub.add_parser("search", help="search the index (F4, F5)")
    search_p.add_argument("query")
    search_p.add_argument("--limit", type=int, default=20, help="max results (F7)")
    search_p.add_argument(
        "-C",
        "--context",
        type=int,
        default=DEFAULT_CONTEXT_TOKENS,
        help="snippet context size in tokens, like grep -C (F7)",
    )
    search_p.add_argument("--json", action="store_true", dest="as_json", help="output JSON (F7)")
    search_p.add_argument(
        "--semantic",
        action="store_true",
        dest="as_semantic",
        help="semantic (embedding similarity) search instead of keyword FTS5 (F6)",
    )

    sub.add_parser("status", help="show index status (F8)")

    return parser


def _cmd_root(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config(config_path)
    if args.root_command == "add":
        add_root(config, args.path)
        save_config(config, config_path)
        print(f"added root: {Path(args.path).resolve()}")
    elif args.root_command == "remove":
        remove_root(config, args.path)
        save_config(config, config_path)
        print(f"removed root: {Path(args.path).resolve()}")
    else:  # list
        for r in config.roots:
            print(r)
    return 0


def _cmd_exclude(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config(config_path)
    if args.exclude_command == "add":
        add_exclude(config, args.pattern)
        save_config(config, config_path)
        print(f"added exclude pattern: {args.pattern}")
    elif args.exclude_command == "remove":
        remove_exclude(config, args.pattern)
        save_config(config, config_path)
        print(f"removed exclude pattern: {args.pattern}")
    else:  # list
        for p in config.exclude_patterns:
            print(p)
    return 0


def _cmd_index(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config(config_path)
    db_path = resolve_db_path(config, config_path)
    con = open_index(db_path)
    result = reconcile_roots(
        con, [Path(r) for r in config.roots], exclude_patterns=config.exclude_patterns
    )
    print(
        f"indexed {result.indexed} files into {db_path} "
        f"(removed {result.removed} stale entries)"
    )

    if args.as_semantic:
        from sbsearch.embeddings import LocalEmbedder
        from sbsearch.semantic import enable_vector_search, reconcile_roots_semantic

        enable_vector_search(con)
        embedder = LocalEmbedder()
        semantic_result = reconcile_roots_semantic(
            con,
            [Path(r) for r in config.roots],
            embedder,
            exclude_patterns=config.exclude_patterns,
        )
        print(
            f"semantic: indexed {semantic_result.indexed} files "
            f"(removed {semantic_result.removed} stale entries)"
        )
    return 0


def _cmd_watch(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config(config_path)
    if not config.roots:
        print("no roots registered; use `sbsearch root add <path>` first")
        return 1

    db_path = resolve_db_path(config, config_path)
    con = open_index(db_path, check_same_thread=False)

    result = reconcile_roots(
        con, [Path(r) for r in config.roots], exclude_patterns=config.exclude_patterns
    )
    print(f"reconciled: indexed {result.indexed}, removed {result.removed} stale entries")

    watcher = IndexWatcher(
        con,
        [Path(r) for r in config.roots],
        exclude_patterns=config.exclude_patterns,
        debounce_seconds=DEFAULT_DEBOUNCE_SECONDS,
    )
    watcher.start()
    print(f"watching {len(config.roots)} root(s) for changes (Ctrl+C to stop)...")
    try:
        if args.timeout is not None:
            time.sleep(args.timeout)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
    return 0


def _cmd_search(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config(config_path)
    db_path = resolve_db_path(config, config_path)
    con = open_index(db_path)

    if args.as_semantic:
        from sbsearch.embeddings import LocalEmbedder
        from sbsearch.semantic import enable_vector_search, semantic_search

        enable_vector_search(con)
        embedder = LocalEmbedder()
        results = semantic_search(con, args.query, embedder, limit=args.limit)
    else:
        results = search(con, args.query, limit=args.limit, context_tokens=args.context)

    if args.as_json:
        print(json.dumps([r.__dict__ for r in results], ensure_ascii=False))
    else:
        for r in results:
            print(f"{r.path}\n  {r.snippet}\n")
    return 0


def _cmd_status(config_path: Path) -> int:
    config = load_config(config_path)
    db_path = resolve_db_path(config, config_path)
    con = open_index(db_path)
    status = get_status(con, db_path)

    last_indexed = (
        datetime.fromtimestamp(status.last_indexed, tz=timezone.utc).isoformat()
        if status.last_indexed is not None
        else None
    )
    payload = {
        "file_count": status.file_count,
        "last_indexed": last_indexed,
        "db_size_bytes": status.db_size_bytes,
        "db_path": str(db_path),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config_path = Path(args.config)

    if args.command == "root":
        return _cmd_root(args, config_path)
    if args.command == "exclude":
        return _cmd_exclude(args, config_path)
    if args.command == "index":
        return _cmd_index(args, config_path)
    if args.command == "watch":
        return _cmd_watch(args, config_path)
    if args.command == "search":
        return _cmd_search(args, config_path)
    if args.command == "status":
        return _cmd_status(config_path)
    return 1


if __name__ == "__main__":
    sys.exit(main())
