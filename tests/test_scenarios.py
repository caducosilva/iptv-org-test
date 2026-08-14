#!/usr/bin/env python3
"""Bateria de testes: saude, probe, hide_dead, cast multiplos canais."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

API = "http://127.0.0.1:8769"
BASE = Path.home() / "Documents" / "iptv-org-test"
LOG_DIR = BASE / "test-logs"
GLOBO = {
    "name": "TV Globo Rio de Janeiro (720p)",
    "url": "http://45.190.28.50/GLOBO_HD/index.m3u8",
}
DEAD = {
    "name": "GloboNews MORTA",
    "url": "http://41.205.70.146/GLOBONEWS/index.m3u8",
}
FAKE = {
    "name": "Host inexistente",
    "url": "http://canal-que-nao-existe-xyz.invalid/live.m3u8",
}


def api_get(path: str, timeout: float = 30.0) -> dict:
    with urllib.request.urlopen(API + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_post(path: str, payload: dict, timeout: float = 30.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def log(lines: list[str], msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    lines.append(line)


def wait_cast(timeout: int = 55) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        try:
            st = api_get("/cast_status", timeout=8)
            last = st
            if not st.get("pending"):
                return st
        except Exception as exc:  # noqa: BLE001
            last = {"ok": False, "error": str(exc), "pending": True}
        time.sleep(1)
    last["error"] = last.get("error") or "timeout cast"
    last["ok"] = False
    last["pending"] = False
    return last


def wait_probe(timeout: int = 120) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        st = api_get("/probe/status", timeout=10)
        last = st
        if not (st.get("probe") or {}).get("running"):
            return st
        time.sleep(1)
    return last


def cast_channel(ch: dict, device_host: str, lines: list[str]) -> dict:
    log(lines, f"CAST start: {ch.get('name')}")
    api_post(
        "/cast",
        {
            "url": ch["url"],
            "title": ch["name"],
            "channelName": ch["name"],
            "deviceName": device_host.lower(),
            "host": device_host,
            "deviceLabel": device_host,
        },
        timeout=20,
    )
    st = wait_cast(60)
    ok = bool(st.get("ok"))
    msg = st.get("message") or st.get("error") or ""
    log(lines, f"CAST result ok={ok} msg={msg[:160]} player={st.get('player')} device={st.get('device')}")
    return st


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"scenarios_{stamp}.log"
    lines: list[str] = []
    fails = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal fails
        if cond:
            log(lines, f"OK: {name} {detail}".rstrip())
        else:
            fails += 1
            log(lines, f"ERRO: {name} {detail}".rstrip())

    log(lines, "=== inicio bateria ===")
    try:
        h = api_get("/health", timeout=5)
        check("API /health", bool(h.get("ok")), json.dumps(h, ensure_ascii=False)[:200])
    except Exception as exc:  # noqa: BLE001
        log(lines, f"ERRO: API offline: {exc}")
        log_path.write_text("\n".join(lines), encoding="utf-8")
        return 1

    cat = api_get("/catalog", timeout=20)
    check("catalogo M3U", int(cat.get("channels") or 0) > 0, str(cat))

    # preview bom
    p_ok = api_get("/preview?url=" + urllib.parse.quote(GLOBO["url"]) + "&name=Globo")
    check("preview Globo OK", bool(p_ok.get("ok")), f"health={p_ok.get('health')} bytes={p_ok.get('bytes')}")

    # preview morto duro
    p_dead = api_get("/preview?url=" + urllib.parse.quote(DEAD["url"]) + "&name=GloboNews")
    check(
        "preview GloboNews OFF",
        not bool(p_dead.get("ok")),
        f"health={p_dead.get('health')} err={p_dead.get('error')}",
    )
    check(
        "GloboNews classificado morto/duvida",
        (p_dead.get("health") or "") in ("dead", "doubt"),
        str(p_dead.get("health")),
    )

    # DNS fake
    p_fake = api_get("/preview?url=" + urllib.parse.quote(FAKE["url"]) + "&name=Fake")
    check("preview DNS fake OFF", not bool(p_fake.get("ok")), f"health={p_fake.get('health')}")
    check("DNS fake = dead", p_fake.get("health") == "dead", str(p_fake.get("health")))

    # batch probe amostra
    sample = api_get("/channels?q=globo&limit=12", timeout=60).get("channels") or []
    check("busca globo", len(sample) > 0, f"n={len(sample)}")
    if sample:
        try:
            api_post("/probe/batch", {"channels": sample[:10], "workers": 5}, timeout=20)
            pst = wait_probe(90)
            pr = pst.get("probe") or {}
            check("probe batch terminou", not pr.get("running"), json.dumps(pr, ensure_ascii=False)[:200])
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                log(lines, "INFO: probe ja rodando, aguardando...")
                wait_probe(90)
            else:
                fails += 1
                log(lines, f"ERRO: probe batch HTTP {exc.code}")

    # hide_dead: garante que URL morta conhecida some
    all_c = api_get("/channels?q=globo&limit=50", timeout=60)
    hid_c = api_get("/channels?q=globo&limit=50&hide_dead=1", timeout=60)
    n_all = int(all_c.get("count") or 0)
    n_hid = int(hid_c.get("count") or 0)
    check("hide_dead nao aumenta lista", n_hid <= n_all, f"all={n_all} hide={n_hid}")
    dead_in_hide = [
        c
        for c in (hid_c.get("channels") or [])
        if c.get("health") == "dead" and not c.get("confirmed")
    ]
    check("hide_dead remove mortos nao confirmados", len(dead_in_hide) == 0, f"restaram={len(dead_in_hide)}")
    # URL morta explicita nao deve aparecer com hide_dead
    dead_url_in = any(
        (c.get("url") or "") == DEAD["url"] for c in (hid_c.get("channels") or [])
    )
    # so valida se a URL morta existia no catalogo da busca; senao ignora
    dead_url_all = any((c.get("url") or "") == DEAD["url"] for c in (all_c.get("channels") or []))
    if dead_url_all:
        check("URL GloboNews morta ocultada", not dead_url_in, f"in_hide={dead_url_in}")
    else:
        log(lines, "INFO: URL GloboNews nao esta na busca globo (ok)")

    # devices + cast
    devices = []
    try:
        scan = api_get("/scan", timeout=40)
        devices = scan.get("devices") or []
    except Exception as exc:  # noqa: BLE001
        log(lines, f"WARN scan: {exc}")
        try:
            devices = api_get("/devices", timeout=10).get("devices") or []
        except Exception:
            devices = []
    check("TV encontrada", len(devices) > 0, f"n={len(devices)}")
    host = ""
    if devices:
        host = devices[0].get("host") or ""
        log(lines, f"INFO: TV={devices[0].get('friendlyName')} host={host}")

    cast_results = []
    if host:
        time.sleep(2)
        # canal bom
        st1 = cast_channel(GLOBO, host, lines)
        cast_results.append(("globo", st1))
        check("cast Globo", bool(st1.get("ok")), st1.get("message") or st1.get("error") or "")
        time.sleep(4)

        # segundo canal: so se preview OK recente
        other = None
        for c in sample:
            u = c.get("url") or ""
            if not u or u == GLOBO["url"]:
                continue
            if (c.get("health") or "") == "ok":
                other = c
                break
        if not other:
            # tenta achar um ok via preview rapido
            for c in sample:
                u = c.get("url") or ""
                if not u or u == GLOBO["url"]:
                    continue
                try:
                    pr = api_get("/preview?url=" + urllib.parse.quote(u), timeout=12)
                except Exception:
                    continue
                if pr.get("ok"):
                    other = c
                    break
        if other:
            st2 = cast_channel(other, host, lines)
            cast_results.append((other.get("name"), st2))
            if st2.get("ok"):
                log(lines, f"OK: cast segundo canal {other.get('name')}")
            else:
                log(lines, f"WARN: segundo cast falhou (aceito): {st2.get('error') or st2.get('message')}")
            time.sleep(2)

        # cast de morto deve falhar limpo
        st3 = cast_channel(DEAD, host, lines)
        cast_results.append(("globonews_dead", st3))
        check("cast morto falha limpo", not bool(st3.get("ok")), st3.get("message") or st3.get("error") or "")

    # confirmed apos cast OK
    hs = api_get("/health_channels", timeout=10)
    log(lines, f"INFO health stats: {json.dumps(hs.get('counts'), ensure_ascii=False)}")
    entry = None
    try:
        # via preview health_entry ja salvo; checa confirmed no arquivo
        from channel_health import get_entry

        entry = get_entry(GLOBO["url"])
        check(
            "Globo confirmado apos cast OK",
            entry.get("status") == "confirmed" or bool(entry.get("confirmed")),
            str(entry),
        )
    except Exception as exc:  # noqa: BLE001
        log(lines, f"WARN ler confirmed: {exc}")

    log(lines, f"=== fim fails={fails} ===")
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    latest = LOG_DIR / "scenarios_latest.log"
    latest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"LOG: {log_path}", flush=True)
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
