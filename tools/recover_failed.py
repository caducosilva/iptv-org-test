#!/usr/bin/env python3
"""Retesta canais falhos com UA alternativo e TLS inseguro; recupera o que der."""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# reusa parser do probe
sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_m3u import USER_AGENTS, parse_m3u, write_m3u, ProbeResult  # noqa: E402


def try_get(url: str, headers: dict[str, str], insecure: bool, timeout: float = 10.0):
    ctx = ssl._create_unverified_context() if insecure else None
    req = Request(url, method="GET", headers=headers)
    t0 = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout, context=ctx) as resp:
            chunk = resp.read(2048)
            code = resp.getcode()
            ok = code < 400 and len(chunk) > 0
            return ok, code, f"HTTP {code}", int((time.perf_counter() - t0) * 1000)
    except HTTPError as exc:
        return False, exc.code, f"HTTP {exc.code}", int((time.perf_counter() - t0) * 1000)
    except Exception as exc:  # noqa: BLE001
        return False, None, f"{type(exc).__name__}: {exc}", int((time.perf_counter() - t0) * 1000)


def main() -> int:
    base = Path.home() / "Documents" / "iptv-org-test"
    failed_m3u = base / "results-br" / "failed_latest.m3u"
    working_m3u = base / "results-br" / "working_latest.m3u"
    out_dir = base / "results-br"
    channels = parse_m3u(failed_m3u)
    recovered: list[ProbeResult] = []
    still_bad: list[ProbeResult] = []

    combos = [
        ("vlc", False),
        ("chrome", False),
        ("vlc", True),
        ("chrome", True),
        ("iptvnator", True),
    ]

    for i, ch in enumerate(channels, 1):
        ok = False
        detail = ""
        code = None
        ua_used = USER_AGENTS["vlc"]
        latency = 0
        status = "STILL_FAIL"
        for ua_name, insecure in combos:
            headers = {
                "User-Agent": ch.user_agent or USER_AGENTS[ua_name],
                "Accept": "*/*",
                "Connection": "close",
            }
            if ch.referrer:
                headers["Referer"] = ch.referrer
            ok, code, detail, latency = try_get(ch.url, headers, insecure)
            if ok:
                ua_used = headers["User-Agent"]
                status = f"RECOVERED_UA={ua_name}_TLS={'off' if insecure else 'on'}"
                break
        row = ProbeResult(
            name=ch.name,
            url=ch.url,
            ok=ok,
            status=status,
            detail=detail[:400],
            http_code=code,
            user_agent_used=ua_used,
            latency_ms=latency,
            extinf=ch.extinf,
            options=ch.options,
        )
        mark = "OK" if ok else "ERRO"
        print(f"[{i}/{len(channels)}] {mark}: [{status}] {ch.name} | {detail}")
        if ok:
            recovered.append(row)
        else:
            still_bad.append(row)

    # merge recovered into working
    already = parse_m3u(working_m3u)
    from probe_m3u import Channel

    merged_results = []
    for ch in already:
        merged_results.append(
            ProbeResult(
                name=ch.name,
                url=ch.url,
                ok=True,
                status="OK_PREV",
                detail="",
                http_code=200,
                user_agent_used=ch.user_agent or USER_AGENTS["vlc"],
                latency_ms=0,
                extinf=ch.extinf,
                options=ch.options,
            )
        )
    merged_results.extend(recovered)

    fixed_path = out_dir / "working_fixed.m3u"
    still_path = out_dir / "failed_after_fix.m3u"
    write_m3u(fixed_path, merged_results)
    write_m3u(still_path, still_bad)
    # sobrescreve latest com fixed
    fixed_path.replace(out_dir / "working_latest.m3u") if False else None
    import shutil

    shutil.copy2(fixed_path, out_dir / "working_latest.m3u")
    report = {
        "recovered": len(recovered),
        "still_fail": len(still_bad),
        "working_total": len(merged_results),
        "recovered_items": [
            {"name": r.name, "status": r.status, "url": r.url} for r in recovered
        ],
    }
    (out_dir / "recovery_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"INFO: recovered={len(recovered)} still_fail={len(still_bad)} working={len(merged_results)}")
    print(f"OK: {fixed_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
