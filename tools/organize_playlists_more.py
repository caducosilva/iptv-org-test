#!/usr/bin/env python3
"""Importa e organiza listas iptv-org (categorias, idiomas, paises) no IPTVnator."""

from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

UA = "VLC/3.0.20 LibVLC/3.0.20"

LISTAS = [
    # categorias
    ("01 Noticias", "cat-news.m3u", "https://iptv-org.github.io/iptv/categories/news.m3u"),
    ("02 Esportes", "cat-sports.m3u", "https://iptv-org.github.io/iptv/categories/sports.m3u"),
    ("03 Filmes", "cat-movies.m3u", "https://iptv-org.github.io/iptv/categories/movies.m3u"),
    ("04 Infantil", "cat-kids.m3u", "https://iptv-org.github.io/iptv/categories/kids.m3u"),
    ("05 Entretenimento", "cat-entertainment.m3u", "https://iptv-org.github.io/iptv/categories/entertainment.m3u"),
    ("06 Musica", "cat-music.m3u", "https://iptv-org.github.io/iptv/categories/music.m3u"),
    ("07 Documentarios", "cat-documentary.m3u", "https://iptv-org.github.io/iptv/categories/documentary.m3u"),
    # idiomas
    ("08 Portugues", "lang-por.m3u", "https://iptv-org.github.io/iptv/languages/por.m3u"),
    ("09 Ingles", "lang-eng.m3u", "https://iptv-org.github.io/iptv/languages/eng.m3u"),
    ("10 Espanhol", "lang-spa.m3u", "https://iptv-org.github.io/iptv/languages/spa.m3u"),
    # paises
    ("11 Brasil", "country-br.m3u", "https://iptv-org.github.io/iptv/countries/br.m3u"),
    ("12 Portugal", "country-pt.m3u", "https://iptv-org.github.io/iptv/countries/pt.m3u"),
    ("13 Estados Unidos", "country-us.m3u", "https://iptv-org.github.io/iptv/countries/us.m3u"),
    ("14 Argentina", "country-ar.m3u", "https://iptv-org.github.io/iptv/countries/ar.m3u"),
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


def build_payload(pid: str, title: str, url: str | None, header: dict, items: list[dict]) -> dict:
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
        "autoRefresh": True,
        "epgUrls": [],
        "detectedEpgUrls": [],
        "url": url,
        "recentlyViewed": [],
        "manualEpgUrls": [],
        "disabledEpgUrls": [],
        "userAgent": UA,
    }


def main() -> int:
    home = Path.home()
    lists_dir = home / "Documents" / "iptv-org-test" / "lists"
    db = home / ".iptvnator" / "databases" / "iptvnator.db"
    working = home / "Documents" / "iptv-org-test" / "iptvnator-working-br.m3u"
    now_ms = int(time.time() * 1000)

    conn = sqlite3.connect(db, timeout=60)
    conn.execute("DELETE FROM playlists")
    print("INFO: playlists limpas", flush=True)

    position = 0
    for title, filename, url in LISTAS:
        path = lists_dir / filename
        if not path.exists():
            print(f"ERRO: falta {path}", flush=True)
            return 1
        print(f"INFO: parse {title} ...", flush=True)
        header, items = parse_m3u_items(path)
        pid = str(uuid.uuid4())
        payload = build_payload(pid, title, url, header, items)
        conn.execute(
            """INSERT INTO playlists (
                id, name, type, userAgent, origin, filePath, url, count,
                autoRefresh, date_created, last_updated, import_date, update_date,
                position, payload
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pid,
                title,
                "m3u-url",
                UA,
                "url",
                None,
                url,
                len(items),
                1,
                now_ms,
                now_ms,
                now_ms,
                now_ms,
                position,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        print(f"OK: {title} canais={len(items)} pos={position}", flush=True)
        position += 1

    if working.exists():
        print("INFO: parse BR working filtrada ...", flush=True)
        header, items = parse_m3u_items(working)
        pid = str(uuid.uuid4())
        payload = build_payload(pid, "15 BR working (filtrada)", None, header, items)
        payload["url"] = None
        payload["filePath"] = str(working)
        conn.execute(
            """INSERT INTO playlists (
                id, name, type, userAgent, origin, filePath, url, count,
                autoRefresh, date_created, last_updated, import_date, update_date,
                position, payload
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pid,
                "15 BR working (filtrada)",
                "m3u-file",
                UA,
                "file",
                str(working),
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
        print(f"OK: 15 BR working canais={len(items)}", flush=True)

    conn.commit()
    print("--- ordem final ---", flush=True)
    for r in conn.execute("SELECT position, name, count, type FROM playlists ORDER BY position"):
        print(f"{r[0]:>2} | {r[1]:<28} | {r[2]:>6} | {r[3]}", flush=True)
    conn.close()
    print("OK: organizado", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
