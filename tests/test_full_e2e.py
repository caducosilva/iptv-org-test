#!/usr/bin/env python3
"""Bateria E2E completa: API + frontend + cast + saude + favoritos + restart."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

API = "http://127.0.0.1:8769"
FE = "http://127.0.0.1:3000"
BASE = Path(__file__).resolve().parent.parent
LOG_DIR = BASE / "logs" / "test-logs"
FAV_FILE = BASE / "tests" / "test-favorites-sim.json"

GLOBO = {
    "name": "TV Globo Rio de Janeiro (720p)",
    "url": "http://45.190.28.50/GLOBO_HD/index.m3u8",
}
BOI = {
    "name": "Canal do Boi (720p)",
    "url": "http://45.162.64.114/CANAL_DO_BOI/index.m3u8",
}
DEAD = {
    "name": "GloboNews MORTA",
    "url": "http://41.205.70.146/GLOBONEWS/index.m3u8",
}
FAKE = {
    "name": "Host inexistente",
    "url": "http://canal-que-nao-existe-xyz.invalid/live.m3u8",
}


class Runner:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.fails = 0
        self.warns = 0
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = LOG_DIR / f"e2e_full_{self.stamp}.log"

    def log(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        self.lines.append(line)

    def ok(self, name: str, detail: str = "") -> None:
        self.log(f"OK: {name} {detail}".rstrip())

    def err(self, name: str, detail: str = "") -> None:
        self.fails += 1
        self.log(f"ERRO: {name} {detail}".rstrip())

    def warn(self, name: str, detail: str = "") -> None:
        self.warns += 1
        self.log(f"WARN: {name} {detail}".rstrip())

    def check(self, name: str, cond: bool, detail: str = "") -> bool:
        if cond:
            self.ok(name, detail)
            return True
        self.err(name, detail)
        return False

    def save(self) -> None:
        text = "\n".join(self.lines) + "\n"
        self.log_path.write_text(text, encoding="utf-8")
        (LOG_DIR / "e2e_full_latest.log").write_text(text, encoding="utf-8")
        self.log(f"LOG salvo: {self.log_path}")


def api_get(path: str, timeout: float = 60.0) -> dict:
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


def http_status(url: str, timeout: float = 8.0) -> int:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return int(resp.status)


def wait_cast(r: Runner, timeout: int = 55) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        try:
            st = api_get("/cast_status", timeout=8)
            last = st
            phase = st.get("phase") or ""
            if st.get("pending"):
                r.log(f"  cast pending phase={phase} t={int(timeout - (deadline - time.time()))}s")
            else:
                return st
        except Exception as exc:  # noqa: BLE001
            last = {"ok": False, "error": str(exc), "pending": True}
            r.log(f"  cast_status err: {exc}")
        time.sleep(1)
    last["ok"] = False
    last["error"] = last.get("error") or "timeout cast"
    last["pending"] = False
    return last


def wait_probe(r: Runner, timeout: int = 100) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        st = api_get("/probe/status", timeout=10)
        last = st
        pr = st.get("probe") or {}
        if pr.get("running"):
            r.log(f"  probe {pr.get('done')}/{pr.get('total')} ok={pr.get('ok')} dead={pr.get('dead')}")
        else:
            return st
        time.sleep(1.2)
    return last


def cast_one(r: Runner, ch: dict, host: str) -> dict:
    r.log(f"CAST >> {ch.get('name')}")
    api_post(
        "/cast",
        {
            "url": ch["url"],
            "title": ch["name"],
            "channelName": ch["name"],
            "deviceName": host.lower(),
            "host": host,
            "deviceLabel": f"TV @ {host}",
        },
        timeout=20,
    )
    st = wait_cast(r, 55)
    r.log(
        f"CAST << ok={st.get('ok')} player={st.get('player')} msg={(st.get('message') or st.get('error') or '')[:140]}"
    )
    return st


def kill_stack(r: Runner) -> None:
    r.log("RESTART: matando stack...")
    cmds = [
        ["taskkill", "/IM", "IPTVnator.exe", "/F"],
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-CimInstance Win32_Process | Where-Object { "
                "$_.CommandLine -match 'iptvnator_companion\\.py|cast_dock_window\\.py' "
                "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
            ),
        ],
    ]
    for c in cmds:
        subprocess.run(c, capture_output=True, check=False)
    time.sleep(2.5)


def start_stack(r: Runner) -> bool:
    r.log("RESTART: subindo companion integrado...")
    py = Path.home() / "AppData" / "Local" / "hermes" / "hermes-agent" / "venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    script = BASE / "iptvnator_companion.py"
    subprocess.Popen(
        [str(py), str(script)],
        cwd=str(BASE),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 90
    api_ok = fe_ok = False
    while time.time() < deadline:
        try:
            h = api_get("/health", timeout=3)
            api_ok = bool(h.get("ok"))
        except Exception:
            api_ok = False
        try:
            fe_ok = http_status(FE + "/") == 200
        except Exception:
            fe_ok = False
        if api_ok and fe_ok:
            r.ok("stack reiniciada", f"api={api_ok} fe={fe_ok}")
            return True
        time.sleep(1.5)
    r.err("stack reiniciada", f"api={api_ok} fe={fe_ok}")
    return False


def test_favorites_sim(r: Runner) -> None:
    """Simula o contrato de favoritos do frontend (localStorage)."""
    r.log("--- FAVORITOS (contrato front) ---")
    # front usa chave: name|||url ou so url
    favs = [f"{GLOBO['name']}|||{GLOBO['url']}", BOI["url"]]
    FAV_FILE.write_text(json.dumps(favs, ensure_ascii=False, indent=2), encoding="utf-8")
    loaded = json.loads(FAV_FILE.read_text(encoding="utf-8"))
    r.check("favoritos gravar/ler", loaded == favs, str(loaded))
    # filtro mental: canal esta em favoritos
    def is_fav(ch: dict) -> bool:
        key = f"{ch.get('name')}|||{ch.get('url')}"
        return key in loaded or ch.get("url") in loaded

    r.check("Globo e favorito", is_fav(GLOBO))
    r.check("Boi e favorito", is_fav(BOI))
    r.check("Dead nao e favorito", not is_fav(DEAD))
    # remove
    loaded = [x for x in loaded if GLOBO["url"] not in x]
    FAV_FILE.write_text(json.dumps(loaded, ensure_ascii=False), encoding="utf-8")
    r.check("remover favorito Globo", not is_fav(GLOBO) and is_fav(BOI), str(loaded))


def main() -> int:
    r = Runner()
    r.log("=== E2E FULL START ===")

    # 1) stack basica
    r.log("--- STACK ---")
    try:
        h = api_get("/health", timeout=3)
    except Exception:
        r.log("API nao estava rodando; iniciando stack...")
        if not start_stack(r):
            r.save()
            return 1
        h = api_get("/health", timeout=5)
    r.check("API /health", bool(h.get("ok")), json.dumps(h, ensure_ascii=False)[:180])
    try:
        r.check("Frontend :3000", http_status(FE + "/") == 200)
        # asset bundle
        html = urllib.request.urlopen(FE + "/", timeout=5).read().decode("utf-8", "replace")
        r.check("index.html tem root", "root" in html.lower() or "script" in html.lower(), html[:80])
    except Exception as exc:  # noqa: BLE001
        r.err("Frontend", str(exc))

    # 2) catalogo / playlists / channels
    r.log("--- CATALOGO ---")
    cat = api_get("/catalog", timeout=20)
    r.check("catalogo canais>0", int(cat.get("channels") or 0) > 0, str(cat))
    pls = api_get("/playlists", timeout=20)
    r.check("playlists>0", len(pls.get("playlists") or []) > 0, f"n={len(pls.get('playlists') or [])}")
    ch_all = api_get("/channels?q=&limit=200", timeout=90)
    r.check("channels list", int(ch_all.get("count") or 0) > 0, f"n={ch_all.get('count')}")
    # health fields presentes
    sample = (ch_all.get("channels") or [{}])[0]
    r.check("campo health no canal", "health" in sample, str(sample.keys()))

    # 3) busca
    r.log("--- BUSCA ---")
    globo_hits = api_get("/channels?q=globo&limit=20", timeout=60)
    r.check("busca globo", int(globo_hits.get("count") or 0) > 0, f"n={globo_hits.get('count')}")
    boi_hits = api_get("/channels?q=boi&limit=10", timeout=30)
    r.check("busca boi", int(boi_hits.get("count") or 0) > 0, f"n={boi_hits.get('count')}")

    # 4) preview / sinal
    r.log("--- PREVIEW / SINAL ---")
    p_ok = api_get("/preview?url=" + urllib.parse.quote(GLOBO["url"]) + "&name=Globo")
    r.check("preview Globo OK", bool(p_ok.get("ok")), f"health={p_ok.get('health')} bytes={p_ok.get('bytes')}")
    p_boi = api_get("/preview?url=" + urllib.parse.quote(BOI["url"]) + "&name=Boi")
    r.check("preview Boi OK", bool(p_boi.get("ok")), f"health={p_boi.get('health')}")
    p_dead = api_get("/preview?url=" + urllib.parse.quote(DEAD["url"]) + "&name=Dead")
    r.check("preview morto OFF", not bool(p_dead.get("ok")), f"health={p_dead.get('health')} err={p_dead.get('error')}")
    r.check("morto=dead", (p_dead.get("health") or "") in ("dead", "doubt"), str(p_dead.get("health")))
    p_fake = api_get("/preview?url=" + urllib.parse.quote(FAKE["url"]) + "&name=Fake")
    r.check("preview DNS fake OFF", not bool(p_fake.get("ok")), f"health={p_fake.get('health')}")

    # 5) hide_dead
    r.log("--- HIDE DEAD ---")
    a = api_get("/channels?q=globo&limit=50", timeout=60)
    b = api_get("/channels?q=globo&limit=50&hide_dead=1", timeout=60)
    r.check("hide_dead reduz/igual", int(b.get("count") or 0) <= int(a.get("count") or 0), f"{a.get('count')}->{b.get('count')}")
    dead_left = [
        c
        for c in (b.get("channels") or [])
        if c.get("health") == "dead" and not c.get("confirmed")
    ]
    r.check("sem mortos no hide", len(dead_left) == 0, f"restaram={len(dead_left)}")

    # 6) probe batch
    r.log("--- PROBE BATCH ---")
    batch = (globo_hits.get("channels") or [])[:8]
    if batch:
        try:
            # espera probe background livre
            for _ in range(40):
                if not (api_get("/probe/status").get("probe") or {}).get("running"):
                    break
                time.sleep(1)
            api_post("/probe/batch", {"channels": batch, "workers": 5}, timeout=20)
            pst = wait_probe(r, 90)
            pr = pst.get("probe") or {}
            r.check("probe terminou", not pr.get("running"), json.dumps(pr, ensure_ascii=False)[:200])
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                r.warn("probe ocupado", "aguardando...")
                wait_probe(r, 90)
            else:
                r.err("probe batch", f"HTTP {exc.code}")
    hs = api_get("/health_channels", timeout=10)
    r.log(f"INFO counts={json.dumps(hs.get('counts'), ensure_ascii=False)}")

    # 7) favoritos
    test_favorites_sim(r)

    # 8) devices / scan
    r.log("--- DEVICES / SCAN ---")
    try:
        scan = api_get("/scan", timeout=45)
        devices = scan.get("devices") or []
        r.check("scan TV", len(devices) > 0, f"n={len(devices)}")
    except Exception as exc:  # noqa: BLE001
        r.warn("scan", str(exc))
        devices = api_get("/devices", timeout=10).get("devices") or []
        r.check("devices fallback", len(devices) > 0, f"n={len(devices)}")
    host = (devices[0].get("host") if devices else "") or ""
    if host:
        r.log(f"INFO TV={devices[0].get('friendlyName')} host={host}")

    # 9) cast multiplo
    r.log("--- CAST ---")
    if not host:
        r.err("cast", "sem TV")
    else:
        st1 = cast_one(r, GLOBO, host)
        r.check("cast Globo", bool(st1.get("ok")), st1.get("message") or st1.get("error") or "")
        time.sleep(3)
        st2 = cast_one(r, BOI, host)
        r.check("cast Canal do Boi", bool(st2.get("ok")), st2.get("message") or st2.get("error") or "")
        time.sleep(2)
        st3 = cast_one(r, DEAD, host)
        r.check("cast morto falha", not bool(st3.get("ok")), st3.get("message") or st3.get("error") or "")

        # confirmed
        from channel_health import get_entry

        e = get_entry(GLOBO["url"])
        r.check(
            "Globo confirmed apos cast",
            e.get("status") == "confirmed" or bool(e.get("confirmed")),
            str(e.get("status")),
        )
        e2 = get_entry(BOI["url"])
        r.check(
            "Boi confirmed apos cast",
            e2.get("status") == "confirmed" or bool(e2.get("confirmed")),
            str(e2.get("status")),
        )

    # 10) cast_log
    r.log("--- CAST LOG ---")
    try:
        clog = api_get("/cast_log", timeout=10)
        logs = clog.get("logs") or []
        r.check("cast_log tem entradas", len(logs) > 0, f"n={len(logs)}")
        r.log(f"INFO ultimos logs: {json.dumps(logs[-3:], ensure_ascii=False)[:300]}")
    except Exception as exc:  # noqa: BLE001
        r.err("cast_log", str(exc))

    # 11) catalog reload
    r.log("--- CATALOG RELOAD ---")
    reloaded = api_get("/catalog/reload", timeout=60)
    r.check("catalog reload", "version" in reloaded, str(reloaded))

    # 12) lookup
    r.log("--- LOOKUP ---")
    try:
        hit = api_get("/lookup?name=" + urllib.parse.quote("globo"), timeout=20)
        r.check("lookup globo", bool(hit.get("url")), str(hit.get("name")))
    except Exception as exc:  # noqa: BLE001
        r.err("lookup", str(exc))

    # 13) fechar / reabrir
    r.log("--- FECHAR / REABRIR ---")
    kill_stack(r)
    time.sleep(1)
    api_down = False
    try:
        api_get("/health", timeout=2)
    except Exception:
        api_down = True
    r.check("API caiu apos kill", api_down)
    if not start_stack(r):
        r.save()
        return 1
    time.sleep(2)
    # pos-restart smoke
    h2 = api_get("/health", timeout=5)
    r.check("API pos-restart", bool(h2.get("ok")))
    r.check("FE pos-restart", http_status(FE + "/") == 200)
    ch2 = api_get("/channels?q=globo&limit=5", timeout=60)
    r.check("channels pos-restart", int(ch2.get("count") or 0) > 0)
    # cast pos-restart
    devices2 = api_get("/devices", timeout=15).get("devices") or []
    if not devices2:
        try:
            devices2 = api_get("/scan", timeout=45).get("devices") or []
        except Exception:
            devices2 = []
    host2 = (devices2[0].get("host") if devices2 else "") or host
    if host2:
        st4 = cast_one(r, GLOBO, host2)
        r.check("cast Globo pos-restart", bool(st4.get("ok")), st4.get("message") or st4.get("error") or "")
    else:
        r.warn("cast pos-restart", "TV nao vista ainda")

    r.log(f"=== E2E FULL END fails={r.fails} warns={r.warns} ===")
    r.save()
    return 0 if r.fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
