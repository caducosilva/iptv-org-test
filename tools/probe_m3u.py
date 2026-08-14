#!/usr/bin/env python3
"""Testa canais de uma playlist M3U e gera M3U filtrada + log."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENTS = {
    "vlc": "VLC/3.0.20 LibVLC/3.0.20",
    "chrome": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "iptvnator": "IPTVnator/0.22.0",
}

DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Connection": "close",
}


@dataclass
class Channel:
    name: str
    url: str
    extinf: str
    options: list[str]
    referrer: str | None = None
    user_agent: str | None = None


@dataclass
class ProbeResult:
    name: str
    url: str
    ok: bool
    status: str
    detail: str
    http_code: int | None
    user_agent_used: str
    latency_ms: int
    extinf: str
    options: list[str]


def parse_m3u(path: Path) -> list[Channel]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    channels: list[Channel] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("#EXTINF:"):
            i += 1
            continue
        extinf = line
        options: list[str] = []
        referrer = None
        user_agent = None
        i += 1
        while i < len(lines) and lines[i].startswith("#"):
            opt = lines[i]
            options.append(opt)
            low = opt.lower()
            if "http-referrer=" in low or "http-referer=" in low:
                referrer = opt.split("=", 1)[-1].strip()
            if "http-user-agent=" in low:
                user_agent = opt.split("=", 1)[-1].strip()
            i += 1
        if i >= len(lines):
            break
        url = lines[i]
        i += 1
        if url.startswith("#"):
            continue
        m = re.search(r",(.+)$", extinf)
        name = m.group(1).strip() if m else url
        # referrer tambem pode vir no EXTINF
        mref = re.search(r'http-referrer="([^"]+)"', extinf, re.I)
        if mref:
            referrer = mref.group(1)
        mua = re.search(r'http-user-agent="([^"]+)"', extinf, re.I)
        if mua:
            user_agent = mua.group(1)
        channels.append(
            Channel(
                name=name,
                url=url,
                extinf=extinf,
                options=options,
                referrer=referrer,
                user_agent=user_agent,
            )
        )
    return channels


def classify_error(msg: str) -> str:
    low = msg.lower()
    rules = [
        ("timeout", "TIMEOUT"),
        ("timed out", "TIMEOUT"),
        ("403", "HTTP_403"),
        ("401", "HTTP_401"),
        ("404", "HTTP_404"),
        ("410", "HTTP_410"),
        ("451", "HTTP_451_GEO"),
        ("502", "HTTP_502"),
        ("503", "HTTP_503"),
        ("ssl", "TLS_ERROR"),
        ("certificate", "TLS_ERROR"),
        ("name or service not known", "DNS"),
        ("getaddrinfo", "DNS"),
        ("nodename nor servname", "DNS"),
        ("connection refused", "CONN_REFUSED"),
        ("failed to connect", "CONN_FAIL"),
        ("network is unreachable", "NET_UNREACH"),
        ("no route to host", "NET_UNREACH"),
        ("invalid data", "BAD_STREAM"),
        ("end of file", "EOF"),
        ("server returned", "HTTP_ERROR"),
        ("http error", "HTTP_ERROR"),
        ("403 forbidden", "HTTP_403"),
        ("geo", "GEO_BLOCK"),
    ]
    for needle, code in rules:
        if needle in low:
            return code
    return "OTHER"


def http_probe(url: str, headers: dict[str, str], timeout: float) -> tuple[bool, int | None, str]:
    req = Request(url, method="GET", headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", None) or resp.getcode()
            chunk = resp.read(2048)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            text_head = chunk[:200].decode("utf-8", errors="ignore").lower()
            looks_m3u = "#extm3u" in text_head or "#extinf" in text_head or ".ts" in text_head
            looks_media = any(
                x in ctype
                for x in (
                    "mpegurl",
                    "application/vnd.apple",
                    "video/",
                    "audio/",
                    "octet-stream",
                    "application/x-mpeg",
                )
            )
            if code and int(code) >= 400:
                return False, int(code), f"HTTP {code}"
            if looks_m3u or looks_media or len(chunk) > 0:
                return True, int(code) if code else 200, f"HTTP {code}; ctype={ctype or 'n/a'}"
            return False, int(code) if code else None, "empty body"
    except HTTPError as exc:
        return False, int(exc.code), f"HTTP {exc.code}: {exc.reason}"
    except URLError as exc:
        return False, None, f"URLError: {exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return False, None, f"{type(exc).__name__}: {exc}"


def ffprobe_ok(url: str, headers: dict[str, str], timeout: float, ffprobe: str) -> tuple[bool, str]:
    header_lines = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name",
        "-of",
        "json",
        "-rw_timeout",
        str(int(timeout * 1_000_000)),
        "-headers",
        header_lines,
        url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "ffprobe timeout"
    except OSError as exc:
        return False, f"ffprobe OSError: {exc}"

    err = (proc.stderr or "").strip()
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return False, err or f"ffprobe exit {proc.returncode}"
    try:
        data = json.loads(out or "{}")
    except json.JSONDecodeError:
        return False, f"ffprobe bad json: {out[:200]}"
    streams = data.get("streams") or []
    if not streams:
        return False, "ffprobe sem streams"
    kinds = sorted({s.get("codec_type", "?") for s in streams})
    codecs = sorted({s.get("codec_name", "?") for s in streams})
    return True, f"streams={kinds}; codecs={codecs}"


def probe_channel(
    ch: Channel,
    ua_name: str,
    timeout: float,
    ffprobe: str | None,
    deep: bool,
) -> ProbeResult:
    ua = ch.user_agent or USER_AGENTS[ua_name]
    headers = dict(DEFAULT_HEADERS)
    headers["User-Agent"] = ua
    if ch.referrer:
        headers["Referer"] = ch.referrer

    t0 = time.perf_counter()
    ok, code, detail = http_probe(ch.url, headers, timeout)
    status = "OK_HTTP" if ok else classify_error(detail)

    # Tenta User-Agents alternativos se falhar com 403
    if not ok and code in {401, 403, 451}:
        for alt_name, alt_ua in USER_AGENTS.items():
            if alt_ua == ua:
                continue
            headers2 = dict(headers)
            headers2["User-Agent"] = alt_ua
            ok2, code2, detail2 = http_probe(ch.url, headers2, timeout)
            if ok2:
                ok, code, detail = ok2, code2, f"{detail2} (UA={alt_name})"
                ua = alt_ua
                status = "OK_HTTP_UA_FIX"
                break
            status = classify_error(detail2)
            detail = detail2
            code = code2

    if ok and deep and ffprobe:
        fok, fdetail = ffprobe_ok(ch.url, headers if ua == headers["User-Agent"] else {**headers, "User-Agent": ua}, timeout, ffprobe)
        if fok:
            status = "OK_FFPROBE" if status.startswith("OK") else status
            detail = f"{detail} | {fdetail}"
        else:
            ok = False
            status = classify_error(fdetail)
            detail = fdetail

    latency = int((time.perf_counter() - t0) * 1000)
    return ProbeResult(
        name=ch.name,
        url=ch.url,
        ok=ok,
        status=status,
        detail=detail[:500],
        http_code=code,
        user_agent_used=ua,
        latency_ms=latency,
        extinf=ch.extinf,
        options=ch.options,
    )


def write_m3u(path: Path, results: list[ProbeResult]) -> None:
    lines = ["#EXTM3U"]
    for r in results:
        lines.append(r.extinf)
        lines.extend(r.options)
        # Injeta UA se o teste so passou com UA especifico
        if r.user_agent_used and "http-user-agent=" not in "\n".join(r.options).lower():
            lines.append(f"#EXTVLCOPT:http-user-agent={r.user_agent_used}")
        lines.append(r.url)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--ua", choices=sorted(USER_AGENTS), default="vlc")
    ap.add_argument("--deep", action="store_true", help="Usa ffprobe alem do HTTP")
    ap.add_argument("--sample-every", type=int, default=1, help="Pega 1 a cada N canais")
    args = ap.parse_args()

    inp = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = outdir / f"probe_{stamp}.log"
    json_path = outdir / f"probe_{stamp}.json"
    ok_m3u = outdir / f"working_{stamp}.m3u"
    fail_m3u = outdir / f"failed_{stamp}.m3u"

    channels = parse_m3u(inp)
    if args.sample_every > 1:
        channels = channels[:: args.sample_every]
    if args.limit > 0:
        channels = channels[: args.limit]

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        # fallback winget path comum
        winget_guess = Path(os.environ.get("LOCALAPPDATA", "")) / (
            "Microsoft/WinGet/Packages"
        )
        found = list(winget_guess.glob("Gyan.FFmpeg*/**/ffprobe.exe")) if winget_guess.exists() else []
        ffprobe = str(found[0]) if found else None

    lines_log: list[str] = []
    lines_log.append(f"INFO: input={inp}")
    lines_log.append(f"INFO: canais={len(channels)} workers={args.workers} timeout={args.timeout}s ua={args.ua} deep={args.deep}")
    lines_log.append(f"INFO: ffprobe={ffprobe or 'ausente'}")

    results: list[ProbeResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [
            pool.submit(probe_channel, ch, args.ua, args.timeout, ffprobe, args.deep)
            for ch in channels
        ]
        for idx, fut in enumerate(concurrent.futures.as_completed(futs), 1):
            r = fut.result()
            results.append(r)
            mark = "OK" if r.ok else "ERRO"
            line = f"{mark}: [{r.status}] {r.name} | {r.latency_ms}ms | {r.detail} | {r.url}"
            lines_log.append(line)
            print(f"[{idx}/{len(channels)}] {line}", flush=True)

    # Mantem ordem original
    by_url = {r.url: r for r in results}
    ordered = [by_url[ch.url] for ch in channels if ch.url in by_url]
    ok_list = [r for r in ordered if r.ok]
    fail_list = [r for r in ordered if not r.ok]

    counts: dict[str, int] = {}
    for r in ordered:
        counts[r.status] = counts.get(r.status, 0) + 1

    summary = [
        f"INFO: total={len(ordered)} ok={len(ok_list)} fail={len(fail_list)}",
        "INFO: status_counts=" + json.dumps(counts, ensure_ascii=False, sort_keys=True),
    ]
    lines_log.extend(summary)
    for s in summary:
        print(s, flush=True)

    write_m3u(ok_m3u, ok_list)
    write_m3u(fail_m3u, fail_list)
    log_path.write_text("\n".join(lines_log) + "\n", encoding="utf-8")
    json_path.write_text(
        json.dumps([asdict(r) for r in ordered], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Atalhos estaveis
    shutil.copy2(ok_m3u, outdir / "working_latest.m3u")
    shutil.copy2(fail_m3u, outdir / "failed_latest.m3u")
    shutil.copy2(log_path, outdir / "probe_latest.log")
    print(f"OK: log={log_path}")
    print(f"OK: working={ok_m3u}")
    print(f"OK: failed={fail_m3u}")
    return 0 if ok_list else 2


if __name__ == "__main__":
    sys.exit(main())
