#!/usr/bin/env python3
"""Recupera canais TLS/403 com TLS inseguro e UA alternativo."""

from __future__ import annotations

import importlib.util
import json
import shutil
import ssl
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

BASE = Path.home() / "Documents" / "iptv-org-test"
RESULTS = BASE / "results-br"
UAS = [
    "VLC/3.0.20 LibVLC/3.0.20",
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
]


def load_probe():
    spec = importlib.util.spec_from_file_location("probe_m3u", BASE / "probe_m3u.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    js = sorted(RESULTS.glob("probe_*.json"), key=lambda p: p.stat().st_mtime)[-1]
    data = json.loads(js.read_text(encoding="utf-8"))
    targets = [r for r in data if r["status"] in {"TLS_ERROR", "HTTP_403"}]
    print(f"INFO: targets={len(targets)} from {js.name}", flush=True)

    ctx = ssl._create_unverified_context()
    ffprobe = shutil.which("ffprobe")
    recovered = []

    for r in targets:
        ok = False
        used = ""
        detail = ""
        for ua in UAS:
            headers = {"User-Agent": ua, "Accept": "*/*"}
            try:
                req = Request(r["url"], headers=headers)
                with urlopen(req, timeout=8, context=ctx) as resp:
                    chunk = resp.read(2048)
                    if resp.getcode() >= 400 or not chunk:
                        detail = f"HTTP {resp.getcode()}"
                        continue
                if not ffprobe:
                    ok = True
                    used = ua
                    detail = "http-ok-no-ffprobe"
                    break
                cmd = [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "csv=p=0",
                    "-rw_timeout",
                    "8000000",
                    "-tls_verify",
                    "0",
                    "-headers",
                    f"User-Agent: {ua}\r\n",
                    r["url"],
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if proc.returncode == 0 and proc.stdout.strip():
                    ok = True
                    used = ua
                    detail = proc.stdout.strip().replace("\n", ",")
                    break
                detail = (proc.stderr or "ffprobe fail")[:160]
            except Exception as exc:  # noqa: BLE001
                detail = f"{type(exc).__name__}: {exc}"[:160]
        print(f"{'OK' if ok else 'ERRO'}: {r['name']} | {detail}", flush=True)
        if ok:
            recovered.append({**r, "user_agent_used": used, "detail": detail})

    mod = load_probe()
    working = mod.parse_m3u(RESULTS / "working_latest.m3u")
    results = []
    for ch in working:
        results.append(
            mod.ProbeResult(
                ch.name,
                ch.url,
                True,
                "OK",
                "",
                200,
                ch.user_agent or UAS[0],
                0,
                ch.extinf,
                ch.options,
            )
        )
    by_url = {r["url"]: r for r in data}
    for r in recovered:
        src = by_url[r["url"]]
        results.append(
            mod.ProbeResult(
                src["name"],
                src["url"],
                True,
                "RECOVERED_INSECURE_TLS",
                r["detail"],
                200,
                r["user_agent_used"],
                0,
                src["extinf"],
                src["options"],
            )
        )

    out = RESULTS / "working_fixed.m3u"
    mod.write_m3u(out, results)
    shutil.copy2(out, RESULTS / "working_latest.m3u")
    (RESULTS / "recovery_tls.json").write_text(
        json.dumps(
            [{"name": r["name"], "url": r["url"], "ua": r["user_agent_used"]} for r in recovered],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"INFO: recovered={len(recovered)} working_total={len(results)}",
        flush=True,
    )
    print(f"OK: {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
