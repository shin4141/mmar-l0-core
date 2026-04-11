#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from history_store import (
        backup_history_store_file,
        import_history_snapshot,
        load_history_snapshot,
        write_history_snapshot,
    )
except ModuleNotFoundError:
    from tools.history_store import (
        backup_history_store_file,
        import_history_snapshot,
        load_history_snapshot,
        write_history_snapshot,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or import MMAR history snapshots.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Export published history to a JSON snapshot.")
    export_parser.add_argument("--out", required=True, help="Target JSON snapshot path.")

    import_parser = subparsers.add_parser("import", help="Import a JSON snapshot into the current history store.")
    import_parser.add_argument("--in", dest="source_path", required=True, help="Source JSON snapshot path.")
    import_parser.add_argument("--clear-existing", action="store_true", help="Replace existing runs/history items before import.")

    backup_parser = subparsers.add_parser("backup-db", help="Copy the current sqlite history store file.")
    backup_parser.add_argument("--out", required=True, help="Target sqlite copy path.")

    args = parser.parse_args()

    if args.command == "export":
        result = write_history_snapshot(Path(args.out))
    elif args.command == "import":
        snapshot = load_history_snapshot(Path(args.source_path))
        result = import_history_snapshot(snapshot, clear_existing=bool(args.clear_existing))
    else:
        result = backup_history_store_file(Path(args.out))

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
