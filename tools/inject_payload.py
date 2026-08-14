#!/usr/bin/env python3
"""Gera payload IPTVnator a partir de M3U filtrada e atualiza o DB."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

UA = "VLC/3.0.20 LibVLC/3.0.20"


def parse_attr(extinf: str, key: str) -> str:
    m = re.search(rf'{re.escape(key)}="([^"]*)"', extinf, re.I)
    return m.group(1) if m else ""


def parse_m3u_items(path: Path) -> list[dict]:
    lines = [ln.rstrip("\r") for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()]
    items: list[dict] = []
    i = 0
    line_no = 0
    while i < len(lines):
        line_no += 1
        line = lines[i].strip()
        if not line.startswith("#EXTINF:"):
            i += 1
            continue
        extinf = line
        opts: list[str] = []
        i += 1
        while i < len(lines) and lines[i].strip().startswith("#"):
            opts.append(lines[i].strip())
            i += 1
        if i >= len(lines):
            break
        url = lines[i].strip()
        i += 1
        if not url or url.startswith("#"):
            continue
        name_m = re.search(r",(.+)$", extinf)
        name = name_m.group(1).strip() if name_m else url
        referrer = parse_attr(extinf, "http-referrer") or parse_attr(extinf, "http-referer")
        user_agent = parse_attr(extinf, "http-user-agent")
        for opt in opts:
            low = opt.lower()
            if "http-referrer=" in low or "http-referer=" in low:
                referrer = opt.split("=", 1)[-1].strip()
            if "http-user-agent=" in low:
                user_agent = opt.split("=", 1)[-1].strip()
        if not user_agent:
            user_agent = UA
        raw = extinf + "\r\n" + url + "\r"
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
                "raw": raw,
                "line": line_no,
                "catchup": {"type": "", "days": "", "source": ""},
                "timeshift": "",
                "radio": "true" if 'radio="true"' in extinf.lower() else "",
                "id": str(uuid.uuid4()),
            }
        )
    return items


def main() -> int:
    home = Path.home()
    m3u = home / "Documents" / "iptv-org-test" / "iptvnator-working-br.m3u"
    db = home / ".iptvnator" / "databases" / "iptvnator.db"
    items = parse_m3u_items(m3u)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    pid = "1af5e95d-8a58-464f-9d0b-1754fc9e281a"
    payload = {
        "_id": pid,
        "filename": "iptvnator-working-br.m3u",
        "title": "BR working (filtrada)",
        "count": len(items),
        "playlist": {
            "header": {"attrs": {}, "raw": "#EXTM3U"},
            "items": items,
        },
        "importDate": now,
        "lastUsage": now,
        "favorites": [],
        "autoRefresh": False,
        "epgUrls": [],
        "detectedEpgUrls": [],
        "url": None,
        "filePath": str(m3u),
        "recentlyViewed": [],
        "manualEpgUrls": [],
        "disabledEpgUrls": [],
        "userAgent": UA,
    }
    conn = sqlite3.connect(db, timeout=30)
    conn.execute(
        """UPDATE playlists
           SET payload=?, count=?, userAgent=?, name=?, type='m3u-file',
               filePath=?, url=NULL, last_updated=?, update_date=?
           WHERE id=?""",
        (
            json.dumps(payload, ensure_ascii=False),
            len(items),
            UA,
            "BR working (filtrada)",
            str(m3u),
            int(datetime.now().timestamp() * 1000),
            int(datetime.now().timestamp() * 1000),
            pid,
        ),
    )
    # força reimport da URL BR limpando payload antigo do index
    conn.execute(
        """UPDATE playlists
           SET payload=NULL, count=0, last_updated=?, update_date=?
           WHERE id='e8ac4796-1d95-4869-a96a-15ba7d866fb7'""",
        (
            int(datetime.now().timestamp() * 1000),
            int(datetime.now().timestamp() * 1000),
        ),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, name, count, length(payload) FROM playlists WHERE id=?", (pid,)
    ).fetchone()
    print(f"OK: payload items={len(items)} row={row}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
