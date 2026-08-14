#!/usr/bin/env python3
import os
import sqlite3
from pathlib import Path

p = Path.home() / ".iptvnator" / "databases" / "iptvnator.db"
c = sqlite3.connect(p)
print("tables:")
for (name,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"):
    try:
        n = c.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
    except Exception as exc:  # noqa: BLE001
        n = f"err:{exc}"
    print(f"  {name}: {n}")

print("\nplaylists columns/sample:")
cols = [r[1] for r in c.execute("PRAGMA table_info(playlists)")]
print(" cols:", cols)
for row in c.execute("SELECT * FROM playlists LIMIT 5"):
    print(" ", row)

# procura settings
for t in ["settings", "preferences", "config", "app_settings"]:
    exists = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
    ).fetchone()
    if exists:
        print(f"\n{t}:")
        for row in c.execute(f"SELECT * FROM [{t}] LIMIT 20"):
            print(" ", row)
