#!/usr/bin/env python3
"""Testes de integracao front+companion. Gera log em test-logs/."""

from __future__ import annotations

import json
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "test-logs"
API = "http://127.0.0.1:8769"
UI = "http://127.0.0.1:3000"
LOG_DIR.mkdir(parents=True, exist_ok=True)
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG = LOG_DIR / f"integracao_front_{stamp}.log"


# o console do Windows usa cp1252: sem isto, um emoji vindo da UI derruba o teste
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_json(path: str, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(API + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    log(f"INICIO log={LOG}")
    errors: list[str] = []

    try:
        h = get_json("/health", 5)
        log(f"OK /health ok={h.get('ok')} ip={h.get('ip')} devices={h.get('devices')}")
        if not h.get("ok"):
            errors.append("health not ok")
    except Exception as exc:
        errors.append(f"health: {exc}")
        log(f"ERRO /health {exc}")

    try:
        pl = get_json("/playlists", 60)
        n = len(pl.get("playlists") or [])
        log(f"OK /playlists count={n} folder={pl.get('folder')} version={pl.get('version')}")
        if n < 1:
            errors.append("playlists vazio")
    except Exception as exc:
        errors.append(f"playlists: {exc}")
        log(f"ERRO /playlists {exc}")

    try:
        ch = get_json("/channels?limit=20&hide_dead=1", 60)
        channels = ch.get("channels") or []
        log(f"OK /channels n={len(channels)} total={ch.get('total')}")
        if channels:
            log(f"  sample={channels[0].get('name')}")
        else:
            errors.append("channels vazio")
    except Exception as exc:
        errors.append(f"channels: {exc}")
        log(f"ERRO /channels {exc}")

    try:
        dev = get_json("/devices", 15)
        log(f"OK /devices n={len(dev.get('devices') or [])}")
    except Exception as exc:
        errors.append(f"devices: {exc}")
        log(f"ERRO /devices {exc}")

    try:
        with urllib.request.urlopen(UI + "/", timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            has_root = 'id="root"' in html
            log(f"OK UI status={resp.status} html_len={len(html)} has_root={has_root}")
            if "index-" not in html and "assets/" not in html:
                errors.append("UI sem assets")
    except Exception as exc:
        errors.append(f"ui: {exc}")
        log(f"ERRO UI {exc}")

    # Playwright smoke
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.goto(UI + "/", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(4000)
            body = page.evaluate(
                """() => ({
                  text: document.body.innerText.slice(0, 800),
                  children: document.getElementById('root')?.children.length || 0,
                  hasAndroid: document.body.innerText.toLowerCase().includes('espelhar')
                    || document.body.innerText.toLowerCase().includes('favorit')
                    || document.body.innerText.toLowerCase().includes('playlist'),
                })"""
            )
            shot = LOG_DIR / f"integracao_ui_{stamp}.png"
            page.screenshot(path=str(shot), full_page=True)
            log(f"OK playwright children={body['children']} hasAndroidUi={body['hasAndroid']}")
            log(f"  text={body['text'][:350].replace(chr(10), ' | ')}")
            log(f"  screenshot={shot}")
            if page_errors:
                log(f"WARN pageerrors={page_errors[:5]}")
                errors.append("pageerror: " + page_errors[0])
            if body["children"] < 1:
                errors.append("root vazio")
            browser.close()
    except Exception as exc:
        errors.append(f"playwright: {exc}")
        log(f"ERRO playwright {exc}\n{traceback.format_exc()}")

    # assets android (opcional: este projeto nao tem modulo Android)
    www = ROOT / "android-iptv-cast" / "app" / "src" / "main" / "assets" / "www" / "index.html"
    if www.exists():
        log(f"OK android assets index={www} size={www.stat().st_size}")
    else:
        log("SKIP android assets (projeto sem modulo Android)")

    # endpoints de cast novos
    try:
        devices = get_json("/devices").get("devices") or []
        faltando = [d for d in devices if "castable" not in d]
        if faltando:
            errors.append(f"/devices sem flag castable em {len(faltando)} item(s)")
            log(f"ERRO /devices sem castable: {faltando[:2]}")
        else:
            tvs = [d for d in devices if d.get("castable")]
            log(f"OK /devices flags castable presentes ({len(tvs)} TV utilizavel)")
        sem_host = [d for d in devices if not d.get("host")]
        if sem_host:
            errors.append("/devices retornou item sem host (quebra o seletor do front)")
            log(f"ERRO device sem host: {sem_host[:2]}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"/devices: {exc}")
        log(f"ERRO /devices {exc}")

    try:
        req = urllib.request.Request(
            API + "/cast/stop",
            data=json.dumps({"reason": "teste automatizado"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if body.get("ok"):
            log(f"OK /cast/stop responde (stopped={body.get('stopped')})")
        else:
            errors.append("/cast/stop nao respondeu ok")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"/cast/stop: {exc}")
        log(f"ERRO /cast/stop {exc}")

    # cast nunca pode ficar presos em 'pending' apos terminar
    try:
        st = get_json("/cast_status")
        if st.get("pending"):
            errors.append("cast_status ficou pendente apos /cast/stop")
            log(f"ERRO cast pendente: {st.get('message')}")
        else:
            log(f"OK cast_status liberado (phase={st.get('phase')})")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"/cast_status: {exc}")

    if errors:
        log(f"FIM FAIL errors={errors}")
        log("RETCODE: 1")
        return 1
    log("FIM OK")
    log("RETCODE: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
