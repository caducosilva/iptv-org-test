#!/usr/bin/env python3
"""Lista playlists do IPTVnator e opcionalmente atualiza User-Agent / URL."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--set-ua", default=None)
    ap.add_argument("--set-url", default=None)
    ap.add_argument("--playlist-id", default=None)
    ap.add_argument("--name-contains", default=None)
    args = ap.parse_args()

    db = Path.home() / ".iptvnator" / "databases" / "iptvnator.db"
    if not db.exists():
        print(f"ERRO: db nao encontrada: {db}")
        return 1

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, name, type, url, filePath, userAgent, referrer, count, origin FROM playlists ORDER BY position, id"
    ).fetchall()

    if args.list or (not args.set_ua and not args.set_url):
        for r in rows:
            print(
                f"id={r['id']} type={r['type']} count={r['count']} "
                f"ua={r['userAgent']!r} name={r['name']!r} url={r['url']!r} file={r['filePath']!r}"
            )

    targets = rows
    if args.playlist_id:
        targets = [r for r in rows if r["id"] == args.playlist_id]
    elif args.name_contains:
        needle = args.name_contains.lower()
        targets = [r for r in rows if needle in (r["name"] or "").lower()]

    if args.set_ua or args.set_url:
        if not targets:
            print("ERRO: nenhuma playlist alvo")
            return 1
        for r in targets:
            if args.set_ua is not None:
                conn.execute(
                    "UPDATE playlists SET userAgent=? WHERE id=?",
                    (args.set_ua, r["id"]),
                )
                print(f"OK: ua atualizado id={r['id']}")
            if args.set_url is not None:
                conn.execute(
                    "UPDATE playlists SET url=?, filePath=NULL, last_updated=datetime('now') WHERE id=?",
                    (args.set_url, r["id"]),
                )
                print(f"OK: url atualizada id={r['id']}")
        conn.commit()

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
