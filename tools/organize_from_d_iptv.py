#!/usr/bin/env python3
"""Importa playlists locais de D:\\IPTV no IPTVnator."""

from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

UA = "VLC/3.0.20 LibVLC/3.0.20"
IPTV_DIR = Path("D:/IPTV")

# Ordem alinhada a fontes-iptv-org.txt
LISTAS = [
    ("01 Geral por Categoria", "index-category.m3u"),
    ("02 Portugues", "por.m3u"),
    ("03 Brasil", "br.m3u"),
    ("04 Noticias", "news.m3u"),
    ("05 Esportes", "sports.m3u"),
    ("06 Filmes", "movies.m3u"),
    ("07 Infantil", "kids.m3u"),
]


def parse_attr(extinf: str, key: str) -> str:
    m = re.search(rf'{re.escape(key)}="([^"]*)"', extinf, re.I)
    return m.group(1) if m else ""


def parse_m3u_items(path: Path) -> tuple[dict, list[dict]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln.rstrip("\r") for ln in text.splitlines()]
    header_raw = "#EXTM3U"
    header_attrs: dict[str, str] = {}
    items: list[dict] = []
    i = 0
    line_no = 0
    while i < len(lines):
        line_no += 1
        line = lines[i].strip()
        if i == 0 and line.upper().startswith("#EXTM3U"):
            header_raw = line
            for m in re.finditer(r'([\w-]+)="([^"]*)"', line):
                header_attrs[m.group(1)] = m.group(2)
            i += 1
            continue
        if not line.startswith("#EXTINF:"):
            i += 1
            continue
        extinf = line
        i += 1
        while i < len(lines) and lines[i].strip().startswith("#"):
            i += 1
        if i >= len(lines):
            break
        url = lines[i].strip()
        i += 1
        if not url or url.startswith("#"):
            continue
        name_m = re.search(r",(.+)$", extinf)
        name = name_m.group(1).strip() if name_m else url
        if 'http-user-agent="' in extinf.lower():
            name_m2 = re.search(r'group-title="[^"]*",(.+)$', extinf, re.I)
            if name_m2:
                name = name_m2.group(1).strip()
        referrer = parse_attr(extinf, "http-referrer") or parse_attr(extinf, "http-referer")
        user_agent = parse_attr(extinf, "http-user-agent") or UA
        items.append(
            {
                "name": name,
                "tvg": {
                    "id": parse_attr(extinf, "tvg-id"),
                    "name": parse_attr(extinf, "tvg-name"),
                    "logo": parse_attr(extinf, "tvg-logo"),
                    "url": "",
                    "rec": "",
                },
                "group": {"title": parse_attr(extinf, "group-title") or "Undefined"},
                "http": {"referrer": referrer, "user-agent": user_agent},
                "url": url,
                "raw": f"{extinf}\r\n{url}\r",
                "line": line_no,
                "catchup": {"type": "", "days": "", "source": ""},
                "timeshift": "",
                "radio": "true" if 'radio="true"' in extinf.lower() else "",
                "id": str(uuid.uuid4()),
            }
        )
    return {"attrs": header_attrs, "raw": header_raw}, items


def build_payload(pid: str, title: str, file_path: Path, header: dict, items: list[dict]) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return {
        "_id": pid,
        "filename": title,
        "title": title,
        "count": len(items),
        "playlist": {"header": header, "items": items},
        "importDate": now,
        "lastUsage": now,
        "favorites": [],
        "autoRefresh": False,
        "epgUrls": [],
        "detectedEpgUrls": [],
        "url": None,
        "filePath": str(file_path),
        "recentlyViewed": [],
        "manualEpgUrls": [],
        "disabledEpgUrls": [],
        "userAgent": UA,
    }


def insert_playlist(
    conn: sqlite3.Connection,
    title: str,
    path: Path,
    position: int,
    now_ms: int,
) -> None:
    print(f"INFO: parse {title} ...", flush=True)
    header, items = parse_m3u_items(path)
    pid = str(uuid.uuid4())
    payload = build_payload(pid, title, path, header, items)
    conn.execute(
        """INSERT INTO playlists (
            id, name, type, userAgent, origin, filePath, url, count,
            autoRefresh, date_created, last_updated, import_date, update_date,
            position, payload
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            pid,
            title,
            "m3u-file",
            UA,
            "file",
            str(path),
            None,
            len(items),
            0,
            now_ms,
            now_ms,
            now_ms,
            now_ms,
            position,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    print(f"OK: {title} canais={len(items)} pos={position}", flush=True)


def main() -> int:
    if not IPTV_DIR.is_dir():
        print(f"ERRO: pasta inexistente: {IPTV_DIR}", flush=True)
        return 1

    home = Path.home()
    db = home / ".iptvnator" / "databases" / "iptvnator.db"
    working = home / "Documents" / "iptv-org-test" / "iptvnator-working-br.m3u"
    now_ms = int(time.time() * 1000)

    missing = [f for _, f in LISTAS if not (IPTV_DIR / f).exists()]
    if missing:
        print(f"ERRO: faltam arquivos: {missing}", flush=True)
        return 1

    conn = sqlite3.connect(db, timeout=60)
    conn.execute("DELETE FROM playlists")
    print("INFO: playlists limpas", flush=True)

    position = 0
    for title, filename in LISTAS:
        insert_playlist(conn, title, IPTV_DIR / filename, position, now_ms)
        position += 1

    if working.exists():
        insert_playlist(conn, "08 BR working (filtrada)", working, position, now_ms)

    conn.commit()
    print("--- ordem final (origem D:\\IPTV) ---", flush=True)
    for r in conn.execute("SELECT position, name, count, filePath FROM playlists ORDER BY position"):
        print(f"{r[0]:>2} | {r[1]:<28} | {r[2]:>6} | {r[3]}", flush=True)
    conn.close()
    print("OK: organizado a partir do HD externo", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
