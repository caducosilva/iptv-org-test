#!/usr/bin/env python3
"""
Companion IPTVnator:
- forca player externo MPV ao clicar canal (playback que funciona)
- painel: Copy logs / Globo RJ / Scan DLNA / Cast TV
- API local DLNA na rede
"""

from __future__ import annotations

import asyncio
import json
import re
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlparse

import channel_health as chhealth

DEPENDENCIAS = ["websockets", "aiohttp", "async-upnp-client"]


def garantir_dependencias() -> None:
    import importlib.util

    faltando = [d for d in DEPENDENCIAS if importlib.util.find_spec(d.split(".")[0].replace("-", "_") if False else d.replace("-", "_").split(".")[0]) is None]
    # map package names
    mapping = {
        "websockets": "websockets",
        "aiohttp": "aiohttp",
        "async-upnp-client": "async_upnp_client",
    }
    need = []
    for pkg, mod in mapping.items():
        if importlib.util.find_spec(mod) is None:
            need.append(pkg)
    if need:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *need])


garantir_dependencias()

import websockets  # noqa: E402

ROOT = Path(__file__).resolve().parent

CDP_PORT = 9222
API_PORT = 8769
FRONTEND_PORT = 3000
FRONTEND_DIR = ROOT / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"
GLOBO_RJ = "http://45.190.28.50/GLOBO_HD/index.m3u8"
STATE_PATH = ROOT / "dlna_devices.json"

# estado compartilhado
DEVICES: list[dict] = []
LAST_CAST: dict | None = None
CAST_PENDING = False
CAST_LOG: list[dict] = []
CAST_STATE: dict = {
    "phase": "idle",
    "ok": None,
    "message": "aguardando",
    "device": None,
    "url": None,
    "title": None,
    "updatedAt": None,
}
_CAST_LOCK = threading.Lock()
LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
CAST_LOG_PATH = LOGS_DIR / "cast_log.jsonl"
CAST_RESULT_PATH = LOGS_DIR / "cast_result.json"
_LAST_RESULT_FINGERPRINT = ""

# catalogo de listas M3U em pasta local (atualiza sozinho)
_CATALOG_LOCK = threading.Lock()
_CATALOG_PLAYLISTS: list[dict] = []  # {name, file, count, mtime}
_CATALOG_CHANNELS: list[tuple[str, str, str, str, str, str]] = []
# playlist, name, url, group, country (ISO-2 minusculo), logo
_CATALOG_VERSION = 0
_CATALOG_FINGERPRINT = ""


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def cast_log(phase: str, message: str, **extra) -> None:
    """Registra evento de cast (painel + arquivo)."""
    global LAST_CAST, CAST_PENDING
    entry = {
        "ts": _now_iso(),
        "phase": phase,
        "message": message,
        **{k: v for k, v in extra.items() if v is not None},
    }
    with _CAST_LOCK:
        CAST_LOG.append(entry)
        if len(CAST_LOG) > 200:
            del CAST_LOG[:-200]
        CAST_STATE.update(
            {
                "phase": phase,
                "message": message,
                "updatedAt": entry["ts"],
                "ok": extra.get("ok", CAST_STATE.get("ok")),
                "device": extra.get("device", CAST_STATE.get("device")),
                "url": extra.get("url", CAST_STATE.get("url")),
                "title": extra.get("title", CAST_STATE.get("title")),
            }
        )
        if phase in ("started", "running", "connecting"):
            CAST_PENDING = True
        if phase in ("success", "error", "idle"):
            CAST_PENDING = False
        if phase == "success":
            LAST_CAST = dict(CAST_STATE)
        try:
            with CAST_LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
    print(f"CAST[{phase}] {message}", flush=True)


def lists_folder() -> Path:
    """Pasta onde voce joga os .m3u (atualiza sozinho)."""
    cfg = ROOT / "lists_folder.txt"
    if cfg.exists():
        raw = cfg.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        if raw:
            p = Path(raw[0].strip().strip('"'))
            if p.exists():
                return p
    # preferencias: D:\IPTV (HD externo) ou ROOT/lists
    for candidate in (Path("D:/IPTV"), ROOT / "lists", Path.home() / "Documents" / "IPTV"):
        if candidate.exists():
            return candidate
    fallback = ROOT / "lists"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


# Listas do iptv-org usam tvg-id="NomeDoCanal.br@SD": o pedaco depois do
# ultimo ponto (antes do @) e o codigo ISO do pais. E a unica fonte confiavel
# de pais, porque o nome do arquivo .m3u costuma ser categoria (cat-kids),
# idioma (lang-eng) ou lista gigante (index).
_TVG_ID_RE = re.compile(r'tvg-id="([^"]*)"', re.I)
_TVG_LOGO_RE = re.compile(r'tvg-logo="([^"]*)"', re.I)
_GROUP_RE = re.compile(r'group-title="([^"]*)"', re.I)

# arquivos que sao de um pais especifico. Nao entram listas de IDIOMA
# (lang-por pega Brasil e Portugal juntos) nem de categoria.
_PLAYLIST_COUNTRY: dict[str, str] = {
    "br": "br",
    "brasil": "br",
    "brazil": "br",
    "iptvnator-working-br": "br",
    "portugal": "pt",
    "eua": "us",
    "estados-unidos": "us",
    "japao": "jp",
    "japan": "jp",
}

_PLAYLIST_HINT_CACHE: dict[str, str] = {}


def _country_from_tvg_id(tvg_id: str) -> str:
    """'Globo.br@SD' -> 'br'. Retorna '' quando nao da pra saber."""
    base = (tvg_id or "").split("@", 1)[0].strip()
    if "." not in base:
        return ""
    code = base.rsplit(".", 1)[-1].strip().lower()
    if len(code) == 2 and code.isalpha():
        return code
    return ""


def _country_from_playlist(playlist_name: str) -> str:
    """Pais indicado pelo nome do arquivo (country-br.m3u, brasil.m3u)."""
    p = (playlist_name or "").strip().lower()
    if not p:
        return ""
    cached = _PLAYLIST_HINT_CACHE.get(p)
    if cached is not None:
        return cached
    achado = _PLAYLIST_COUNTRY.get(p, "")
    if not achado:
        m = re.match(r"^(?:country|pais|pa[ií]s)[-_]([a-z]{2})$", p)
        if m:
            achado = m.group(1)
    _PLAYLIST_HINT_CACHE[p] = achado
    return achado


def _extinf_name(extinf: str) -> str:
    """
    Nome do canal = o que vem depois da primeira virgula FORA de aspas.
    Pegar a primeira virgula qualquer quebrava canais cujo EXTINF traz
    http-user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) ... (KHTML,
    like Gecko)...", que tem virgula dentro do valor: o nome saia como
    'like Gecko) Chrome/149...'.
    """
    dentro_de_aspas = False
    for i, ch in enumerate(extinf):
        if ch == '"':
            dentro_de_aspas = not dentro_de_aspas
        elif ch == "," and not dentro_de_aspas:
            return extinf[i + 1 :].strip()
    return ""


def _parse_m3u_file(path: Path) -> list[tuple[str, str, str, str, str]]:
    """Retorna lista (name, url, group, country, logo) de um arquivo M3U."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    lines = [ln.rstrip("\r") for ln in text.splitlines()]
    out: list[tuple[str, str, str, str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
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
        name = _extinf_name(extinf) or url
        group_m = _GROUP_RE.search(extinf)
        group = group_m.group(1).strip() if group_m else ""
        tvg_m = _TVG_ID_RE.search(extinf)
        country = _country_from_tvg_id(tvg_m.group(1) if tvg_m else "")
        logo_m = _TVG_LOGO_RE.search(extinf)
        logo = logo_m.group(1).strip() if logo_m else ""
        out.append((name, url, group, country, logo))
    return out


def _folder_fingerprint(folder: Path) -> str:
    parts: list[str] = []
    if not folder.exists():
        return ""
    for p in sorted(folder.glob("*.m3u")) + sorted(folder.glob("*.m3u8")):
        try:
            st = p.stat()
            parts.append(f"{p.name}:{st.st_mtime_ns}:{st.st_size}")
        except OSError:
            continue
    return "|".join(parts)


def reload_lists_catalog(force: bool = False) -> dict:
    """Le a pasta de M3U e atualiza cache se mudou."""
    global _CATALOG_VERSION, _CATALOG_FINGERPRINT, _CATALOG_PLAYLISTS, _CATALOG_CHANNELS
    folder = lists_folder()
    folder.mkdir(parents=True, exist_ok=True)
    fp = _folder_fingerprint(folder)
    with _CATALOG_LOCK:
        if not force and fp == _CATALOG_FINGERPRINT and _CATALOG_CHANNELS:
            return {
                "changed": False,
                "version": _CATALOG_VERSION,
                "folder": str(folder),
                "playlists": len(_CATALOG_PLAYLISTS),
                "channels": len(_CATALOG_CHANNELS),
            }
        playlists: list[dict] = []
        channels: list[tuple[str, str, str, str, str, str]] = []
        files = sorted(folder.glob("*.m3u")) + sorted(folder.glob("*.m3u8"))
        for path in files:
            items = _parse_m3u_file(path)
            pname = path.stem
            playlists.append(
                {
                    "name": pname,
                    "file": path.name,
                    "count": len(items),
                    "mtime": path.stat().st_mtime if path.exists() else 0,
                }
            )
            for name, url, group, country, logo in items:
                # country aqui e so o do tvg-id; o palpite pelo nome do arquivo
                # entra depois, em search_channels, somando-se a ele
                channels.append((pname, name, url, group, country, logo))
        _CATALOG_PLAYLISTS = playlists
        _CATALOG_CHANNELS = channels
        _CATALOG_FINGERPRINT = fp
        _CATALOG_VERSION += 1
        ver = _CATALOG_VERSION
        try:
            invalidate_ranked_cache()
        except Exception:
            pass
        print(
            f"OK: catalogo M3U v{ver} pasta={folder} listas={len(playlists)} canais={len(channels)}",
            flush=True,
        )
        return {
            "changed": True,
            "version": ver,
            "folder": str(folder),
            "playlists": len(playlists),
            "channels": len(channels),
        }


def background_lists_watch(interval: float = 2.0) -> None:
    def loop() -> None:
        while True:
            try:
                reload_lists_catalog(force=False)
            except Exception as exc:  # noqa: BLE001
                print("WARN lists watch:", exc, flush=True)
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True, name="lists-watch").start()


def _iter_playlist_channels():
    """Yield (playlist_name, name, url, group, country, logo) da pasta M3U."""
    with _CATALOG_LOCK:
        data = list(_CATALOG_CHANNELS)
    if data:
        yield from data
        return
    # fallback: IPTVnator DB se pasta ainda vazia
    db = Path.home() / ".iptvnator" / "databases" / "iptvnator.db"
    if not db.exists():
        return
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute("SELECT name, payload FROM playlists ORDER BY position, name").fetchall()
    finally:
        conn.close()
    for playlist_name, payload in rows:
        if not payload:
            continue
        try:
            data_j = json.loads(payload)
        except json.JSONDecodeError:
            continue
        items = (data_j.get("playlist") or {}).get("items") or []
        for it in items:
            cname = (it.get("name") or "").strip()
            url = (it.get("url") or "").strip()
            if not cname or not url:
                continue
            group = ""
            g = it.get("group") or {}
            if isinstance(g, dict):
                group = (g.get("title") or "").strip()
            tvg = it.get("tvg") if isinstance(it.get("tvg"), dict) else {}
            country = _country_from_tvg_id(str(tvg.get("id") or ""))
            logo = str(tvg.get("logo") or "").strip()
            yield playlist_name, cname, url, group, country, logo


def probe_stream(url: str, timeout: float = 8.0, update_health: bool = True, name: str = "") -> dict:
    """Checa se a URL responde como stream (preview/preflight)."""
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "url vazia", "fail_class": "hard"}
    result: dict
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "VLC/3.0.20 LibVLC/3.0.20",
                "Accept": "*/*",
                "Connection": "close",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(262_144)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            status = getattr(resp, "status", 200)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        text = raw.decode("utf-8", "replace")
        looks = (
            "#EXTM3U" in text
            or "mpegurl" in ctype
            or "octet-stream" in ctype
            or "video/" in ctype
            or "audio/" in ctype
            or url.lower().endswith((".m3u8", ".m3u", ".ts", ".mp4"))
            or len(raw) > 200
        )
        if status >= 400:
            fail_class = "hard" if status in (401, 403, 404, 410, 451) else "soft"
            result = {
                "ok": False,
                "error": f"stream invalido HTTP {status}",
                "contentType": ctype,
                "url": url,
                "fail_class": fail_class,
                "http_status": status,
                "latency_ms": round(latency_ms, 1),
            }
        elif not looks:
            result = {
                "ok": False,
                "error": "resposta nao parece stream",
                "contentType": ctype,
                "url": url,
                "fail_class": "soft",
                "bytes": len(raw),
                "latency_ms": round(latency_ms, 1),
            }
        else:
            result = {
                "ok": True,
                "url": url,
                "contentType": ctype,
                "bytes": len(raw),
                "hls": "#EXTM3U" in text,
                "fail_class": "ok",
                "http_status": status,
                "latency_ms": round(latency_ms, 1),
            }
    except Exception as exc:  # noqa: BLE001
        latency_ms = (time.perf_counter() - t0) * 1000.0
        msg = str(exc)
        low = msg.lower()
        if "10061" in msg or "actively refused" in low:
            nice = "canal OFFLINE (servidor recusou conexao)"
            fail_class = "hard"
        elif "timed out" in low or "10060" in msg:
            nice = "canal OFFLINE (timeout)"
            fail_class = "soft"
        elif "getaddrinfo" in low or "11001" in msg:
            nice = "canal OFFLINE (DNS/host inexistente)"
            fail_class = "hard"
        elif "404" in msg:
            nice = "canal OFFLINE (HTTP 404)"
            fail_class = "hard"
        else:
            nice = f"canal OFFLINE ({msg[:120]})"
            fail_class = chhealth.classify_probe_error(msg)
        result = {
            "ok": False,
            "error": nice,
            "detail": msg,
            "url": url,
            "fail_class": fail_class,
            "latency_ms": round(latency_ms, 1),
        }
    if update_health:
        entry = chhealth.apply_probe_result(
            url,
            ok=bool(result.get("ok")),
            error=result.get("error") or "",
            fail_class=result.get("fail_class") or "",
            name=name,
            latency_ms=result.get("latency_ms"),
            bytes_n=result.get("bytes"),
        )
        result["health"] = entry.get("status")
        result["signalStrength"] = entry.get("signal")
        result["health_entry"] = entry
        try:
            chhealth.save_health()
        except Exception:
            pass
    return result


def mpv_exe() -> Path:
    candidates = [
        Path(r"C:\Program Files\MPV Player\mpv.exe"),
        Path(r"C:\Program Files\mpv\mpv.exe"),
        Path.home() / "AppData" / "Local" / "Programs" / "mpv" / "mpv.exe",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def play_in_mpv(url: str, title: str = "IPTV") -> dict:
    """Abre o canal no MPV (player real no PC)."""
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "url vazia"}
    exe = mpv_exe()
    if not exe.exists():
        return {"ok": False, "error": f"MPV nao encontrado em {exe}"}
    title = (title or "IPTV").replace('"', "")
    args = [
        str(exe),
        "--force-window=yes",
        "--hwdec=auto",
        "--cache=yes",
        "--demuxer-max-bytes=64M",
        f"--title={title}",
        "--user-agent=VLC/3.0.20 LibVLC/3.0.20",
        url,
    ]
    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(exe.parent),
        )
        return {
            "ok": True,
            "player": "mpv",
            "url": url,
            "title": title,
            "message": f"MPV aberto: {title}",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def proxy_rewrite_m3u(text: str, base_url: str) -> bytes:
    """Reescreve playlist HLS para passar segmentos pelo proxy local (CORS)."""
    lines_out: list[str] = []
    for line in text.splitlines():
        raw = line.rstrip("\r")
        s = raw.strip()
        if not s:
            lines_out.append(raw)
            continue
        if s.startswith("#"):
            if 'URI="' in s:

                def repl(m: re.Match[str]) -> str:
                    abs_u = urljoin(base_url, m.group(1))
                    prox = f"http://127.0.0.1:{API_PORT}/proxy_media?url={quote(abs_u, safe='')}"
                    return f'URI="{prox}"'

                raw = re.sub(r'URI="([^"]+)"', repl, raw)
            lines_out.append(raw)
            continue
        abs_u = urljoin(base_url, s)
        prox = f"http://127.0.0.1:{API_PORT}/proxy_media?url={quote(abs_u, safe='')}"
        lines_out.append(prox)
    return ("\n".join(lines_out) + "\n").encode("utf-8")


def search_channels(
    query: str,
    limit: int = 40,
    playlist_filter: str | None = None,
) -> list[dict]:
    """Busca canais por nome (independente do que esta tocando no app)."""
    q = (query or "").strip().lower()
    pf = (playlist_filter or "").strip().lower()
    # permite listar quase tudo das playlists M3U
    limit = max(1, min(int(limit or 40), 30000))
    scored: list[tuple[int, dict]] = []
    # url -> canal ja aceito. O mesmo canal aparece em varias listas; a primeira
    # vence, mas as repetidas ainda somam o pais que a lista delas indica.
    seen_urls: dict[str, dict] = {}
    for playlist_name, cname, url, group, country, logo in _iter_playlist_channels():
        if pf and pf not in (playlist_name or "").lower():
            continue
        hint = _country_from_playlist(playlist_name)
        anterior = seen_urls.get(url)
        if anterior is not None:
            # ex.: canal com tvg-id ".us" que tambem esta dentro de br.m3u:
            # ele e visto nos dois paises em vez de sumir do Brasil
            for cc in (country, hint):
                if cc and cc not in anterior["countries"]:
                    anterior["countries"].append(cc)
            continue
        low = cname.lower()
        pl = (playlist_name or "").lower()
        score = 0
        if not q:
            score = 1
        elif low == q:
            score = 100
        elif low.startswith(q):
            score = 90
        elif q in low:
            score = 70
        elif all(tok in low for tok in q.split() if tok):
            score = 55
        else:
            continue
        # prioriza lista filtrada BR e canais estaveis
        if "working" in pl or "filtrada" in pl:
            score += 25
        if "brasil" in pl and "working" not in pl:
            score += 8
        if "rio de janeiro" in low and "globo" in low:
            score += 30
        if "not 24/7" in low or "geo-blocked" in low:
            score -= 20
        # hosts conhecidos mortos
        if "41.205.70.146" in url or "/GLOBONEWS/" in url.upper():
            score -= 40
        paises: list[str] = []
        for cc in (country, hint):
            if cc and cc not in paises:
                paises.append(cc)
        item = {
            "name": cname,
            "url": url,
            "playlist": playlist_name,
            "group": group,
            "country": paises[0] if paises else "",
            "countries": paises,
            "logo": logo,
            "score": score,
        }
        seen_urls[url] = item
        scored.append((score, item))
    if q:
        scored.sort(key=lambda x: (-x[0], x[1]["name"].lower()))
    else:
        scored.sort(key=lambda x: x[1]["name"].lower())
    return [item for _, item in scored[:limit]]



def lookup_channel(name_query: str) -> dict | None:
    """Resolve nome do canal -> URL usando playlists do IPTVnator."""
    q = (name_query or "").strip().lower()
    if not q or len(q) < 2:
        return None
    hits = search_channels(q, limit=8)
    if not hits:
        return None
    # prefer exact / best score from search
    best = hits[0]
    for h in hits:
        if h["name"].lower() == q:
            best = h
            break
    return best


def chromecast_scan(timeout: float = 8.0) -> list[dict]:
    worker = ROOT / "tools" / "scan_worker.py"
    proc = subprocess.run(
        [sys.executable, str(worker)],
        capture_output=True,
        text=True,
        timeout=max(15, int(timeout) + 10),
        check=False,
    )
    out = (proc.stdout or "").strip().splitlines()
    if not out:
        raise RuntimeError((proc.stderr or "").strip() or f"scan_worker exit {proc.returncode}")
    return json.loads(out[-1])


def chromecast_play(host_or_name: str, url: str, title: str = "IPTV") -> dict:
    worker = ROOT / "tools" / "cast_worker.py"
    payload_path = LOGS_DIR / "cast_payload.json"
    result_path = CAST_RESULT_PATH
    if result_path.exists():
        try:
            result_path.unlink()
        except Exception:
            pass
    payload_path.write_text(
        json.dumps(
            {"url": url, "title": title, "deviceName": host_or_name or "philips"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # nao bloqueia o HTTP server: worker grava resultado em arquivo
    wrapper = (
        "import json,subprocess,sys\n"
        f"p=subprocess.run([sys.executable, r'{worker}', r'{payload_path}'], capture_output=True, text=True, timeout=70)\n"
        "lines=(p.stdout or '').strip().splitlines()\n"
        "data=json.loads(lines[-1]) if lines else {'error':'sem output','stderr':p.stderr}\n"
        f"open(r'{result_path}','w',encoding='utf-8').write(json.dumps(data,ensure_ascii=False))\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", wrapper],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # espera resultado ate 55s
    deadline = time.time() + 55
    while time.time() < deadline:
        if result_path.exists():
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                time.sleep(0.3)
                continue
            if data.get("error"):
                raise RuntimeError(data.get("error"))
            if data.get("ok"):
                return data
        time.sleep(0.4)
    raise RuntimeError("timeout aguardando cast na TV")



def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.0.1", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def ssdp_search(timeout: float = 4.0) -> list[dict]:
    """Busca MediaRenderer via SSDP (stdlib)."""
    msg = "\r\n".join(
        [
            "M-SEARCH * HTTP/1.1",
            "HOST: 239.255.255.250:1900",
            'MAN: "ssdp:discover"',
            "MX: 2",
            "ST: urn:schemas-upnp-org:device:MediaRenderer:1",
            "",
            "",
        ]
    ).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout)
    sock.sendto(msg, ("239.255.255.250", 1900))
    found: dict[str, dict] = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            break
        except OSError:
            break
        text = data.decode("utf-8", errors="ignore")
        headers = {}
        for line in text.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().upper()] = v.strip()
        loc = headers.get("LOCATION") or headers.get("Location".upper())
        if not loc:
            continue
        found[loc] = {
            "location": loc,
            "host": addr[0],
            "server": headers.get("SERVER", ""),
            "st": headers.get("ST", ""),
            "usn": headers.get("USN", ""),
        }
    sock.close()

    # tambem rootdevice search
    msg2 = "\r\n".join(
        [
            "M-SEARCH * HTTP/1.1",
            "HOST: 239.255.255.250:1900",
            'MAN: "ssdp:discover"',
            "MX: 2",
            "ST: upnp:rootdevice",
            "",
            "",
        ]
    ).encode("utf-8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(2.5)
    sock.sendto(msg2, ("239.255.255.250", 1900))
    deadline = time.time() + 2.5
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(65535)
        except Exception:
            break
        text = data.decode("utf-8", errors="ignore")
        headers = {}
        for line in text.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().upper()] = v.strip()
        loc = headers.get("LOCATION")
        if loc and loc not in found:
            found[loc] = {
                "location": loc,
                "host": addr[0],
                "server": headers.get("SERVER", ""),
                "st": headers.get("ST", ""),
                "usn": headers.get("USN", ""),
            }
    sock.close()
    return list(found.values())


def fetch_device_info(location: str) -> dict:
    info = {"location": location, "friendlyName": "", "manufacturer": "", "modelName": "", "avt_control": ""}
    try:
        req = urllib.request.Request(location, headers={"User-Agent": "IPTV-DLNA/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            xml = resp.read()
        root = ET.fromstring(xml)
        ns = {"u": "urn:schemas-upnp-org:device-1-0"}
        # sem ns tambem
        def text(tag: str) -> str:
            el = root.find(f".//{{{ns['u']}}}{tag}")
            if el is None:
                el = root.find(f".//{tag}")
            return (el.text or "").strip() if el is not None else ""

        info["friendlyName"] = text("friendlyName")
        info["manufacturer"] = text("manufacturer")
        info["modelName"] = text("modelName")
        base = location.rsplit("/", 1)[0]
        # encontra AVTransport controlURL
        for svc in root.findall(".//{urn:schemas-upnp-org:device-1-0}service") or root.findall(".//service"):
            st = svc.find("{urn:schemas-upnp-org:device-1-0}serviceType")
            if st is None:
                st = svc.find("serviceType")
            cu = svc.find("{urn:schemas-upnp-org:device-1-0}controlURL")
            if cu is None:
                cu = svc.find("controlURL")
            if st is not None and cu is not None and "AVTransport" in (st.text or ""):
                path = (cu.text or "").strip()
                if path.startswith("http"):
                    info["avt_control"] = path
                else:
                    # absolute from host
                    from urllib.parse import urljoin

                    info["avt_control"] = urljoin(location, path)
                break
        info["host"] = urlparse(location).hostname or ""
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)
    return info


def enrich_devices(raw: list[dict]) -> list[dict]:
    out = []
    for d in raw:
        info = fetch_device_info(d["location"])
        info.update({k: d.get(k) for k in ("server", "st", "usn") if d.get(k)})
        out.append(info)
    # prioriza Philips / MediaRenderer com AVT
    def score(x: dict) -> tuple:
        name = (x.get("friendlyName") or "") + (x.get("manufacturer") or "") + (x.get("modelName") or "")
        philips = 0 if "philips" in name.lower() else 1
        avt = 0 if x.get("avt_control") else 1
        return (philips, avt, x.get("friendlyName") or "")

    out.sort(key=score)
    return out


def soap_call(control_url: str, service: str, action: str, body_inner: str) -> str:
    envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
  <s:Body>
    <u:{action} xmlns:u="{service}">
      {body_inner}
    </u:{action}>
  </s:Body>
</s:Envelope>"""
    req = urllib.request.Request(
        control_url,
        data=envelope.encode("utf-8"),
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{service}#{action}"',
            "User-Agent": "IPTV-DLNA/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return resp.read().decode("utf-8", errors="replace")


def xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def didl_meta(url: str, title: str) -> str:
    # DIDL minimo, depois escapado para ir dentro do SOAP
    didl = (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        '<item id="0" parentID="-1" restricted="1">'
        f"<dc:title>{xml_escape(title)}</dc:title>"
        "<upnp:class>object.item.videoItem</upnp:class>"
        f'<res protocolInfo="http-get:*:application/vnd.apple.mpegurl:*">{xml_escape(url)}</res>'
        "</item></DIDL-Lite>"
    )
    return xml_escape(didl)


def cast_to_device(device: dict, url: str, title: str = "IPTV") -> dict:
    control = device.get("avt_control")
    if not control:
        raise RuntimeError("dispositivo sem AVTransport")
    service = "urn:schemas-upnp-org:service:AVTransport:1"
    meta = didl_meta(url, title)
    # SetAVTransportURI
    soap_call(
        control,
        service,
        "SetAVTransportURI",
        f"<InstanceID>0</InstanceID><CurrentURI>{xml_escape(url)}</CurrentURI><CurrentURIMetaData>{meta}</CurrentURIMetaData>",
    )
    # Play
    soap_call(
        control,
        service,
        "Play",
        "<InstanceID>0</InstanceID><Speed>1</Speed>",
    )
    return {"ok": True, "device": device.get("friendlyName"), "url": url}


# --------------------------------------------------------------- cast job

CAST_PORT = 8009
CAST_JOB_TIMEOUT = 150.0  # teto absoluto de um cast (worker espera ~30s no player)
_CAST_PROC: subprocess.Popen | None = None
_CAST_PROC_LOCK = threading.Lock()


def tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    """True se a porta aceita conexao (TV ligada / servico ativo)."""
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:  # noqa: BLE001
        return False


def find_device(needle: str) -> dict | None:
    """Acha o device na lista descoberta por host exato ou nome parcial."""
    needle = (needle or "").strip().lower()
    if not needle:
        return None
    for d in DEVICES:
        if (d.get("host") or "").lower() == needle:
            return d
    for d in DEVICES:
        name = (d.get("friendlyName") or "").lower()
        if name and (needle == name or needle in name or name in needle):
            return d
    return None


def device_is_castable(device: dict) -> bool:
    """Router/gateway/WPS nao sao alvos de cast; TV precisa de Cast ou AVTransport."""
    if not device:
        return False
    if (device.get("type") or "") == "chromecast":
        return True
    avt = (device.get("avt_control") or "").strip()
    if avt and avt != "chromecast":
        return True
    return False


_JUNK_DEVICE_HINTS = (
    "wfadevice",
    "wps",
    "gateway",
    "router",
    "roteador",
    "sagemcom",
    "broadcom",
    "internet gateway",
)


KNOWN_TVS_PATH = ROOT / "known_tvs.json"


def load_known_tvs() -> list[dict]:
    try:
        if KNOWN_TVS_PATH.exists():
            data = json.loads(KNOWN_TVS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict) and d.get("host")]
    except Exception:  # noqa: BLE001
        pass
    return []


def save_known_tvs(devices: list[dict]) -> None:
    """Guarda as TVs ja vistas para elas continuarem na lista quando dormirem."""
    known = {d["host"]: d for d in load_known_tvs()}
    for d in devices:
        if not d.get("castable") or not d.get("host"):
            continue
        known[d["host"]] = {
            "host": d.get("host"),
            "friendlyName": d.get("friendlyName"),
            "manufacturer": d.get("manufacturer"),
            "modelName": d.get("modelName"),
            "type": d.get("type"),
            "avt_control": d.get("avt_control"),
            "lastSeen": _now_iso(),
        }
    try:
        KNOWN_TVS_PATH.write_text(
            json.dumps(list(known.values()), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        print("WARN known_tvs:", exc, flush=True)


def merge_known_tvs(devices: list[dict]) -> list[dict]:
    """Reinsere TVs conhecidas que nao apareceram no scan (TV em standby).

    A Philips fecha a porta 8009 no standby e sumia da lista - o usuario ficava
    sem nada para selecionar. Agora ela aparece marcada como desligada.
    """
    present = {d.get("host") for d in devices}
    out = list(devices)
    for known in load_known_tvs():
        if known.get("host") in present:
            continue
        item = dict(known)
        item["castable"] = True
        item["reachable"] = False
        item["isJunk"] = False
        item["offline"] = True
        item["friendlyName"] = known.get("friendlyName") or f"TV {known.get('host')}"
        out.append(item)
    return out


def normalize_devices(devices: list[dict]) -> list[dict]:
    """Padroniza a lista: host sempre presente, marca o que aceita cast, tira lixo.

    O front usa `host` como chave do seletor - item sem host quebrava a selecao.
    """
    merged: dict[str, dict] = {}
    for d in devices:
        host = (d.get("host") or "").strip()
        if not host:
            loc = d.get("location") or ""
            host = (urlparse(loc).hostname or "").strip() if loc else ""
        if not host:
            continue  # sem endereco nao da pra transmitir
        name = (d.get("friendlyName") or "").strip()
        blob = f"{name} {d.get('manufacturer') or ''} {d.get('modelName') or ''}".lower()
        item = dict(d)
        item["host"] = host
        item["friendlyName"] = name or f"Dispositivo {host}"
        item["castable"] = device_is_castable(d)
        item["isJunk"] = (not item["castable"]) and any(h in blob for h in _JUNK_DEVICE_HINTS)

        # a MESMA TV aparece no Chromecast e no SSDP; junta em um item so
        prev = merged.get(host)
        if prev is None:
            merged[host] = item
            continue
        base, extra = (item, prev) if item["castable"] and not prev["castable"] else (prev, item)
        for key, value in extra.items():
            if value and not base.get(key):
                base[key] = value
        base["castable"] = prev["castable"] or item["castable"]
        base["isJunk"] = prev.get("isJunk", False) and item.get("isJunk", False)
        merged[host] = base

    out: list[dict] = []
    for item in merged.values():
        if item["castable"]:
            item["reachable"] = tcp_open(item["host"], CAST_PORT, timeout=1.2) or str(
                item.get("avt_control") or ""
            ).startswith("http")
        else:
            item["reachable"] = False
        out.append(item)

    save_known_tvs(out)
    out = merge_known_tvs(out)

    def rank(x: dict) -> tuple:
        name = (x.get("friendlyName") or "").lower()
        return (
            0 if x.get("castable") else 1,
            0 if x.get("reachable") else 1,
            0 if ("philips" in name or "pug" in name) else 1,
            1 if x.get("isJunk") else 0,
            name,
        )

    out.sort(key=rank)
    return out


def write_cast_result(data: dict) -> None:
    """Grava cast_result.json de forma atomica."""
    try:
        tmp = CAST_RESULT_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CAST_RESULT_PATH)
    except Exception:  # noqa: BLE001
        try:
            CAST_RESULT_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


def read_cast_result() -> dict | None:
    if not CAST_RESULT_PATH.exists():
        return None
    try:
        return json.loads(CAST_RESULT_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def clear_stale_cast_pending() -> None:
    """Na subida, um 'pending' orfao da sessao anterior vira erro (nao trava a UI)."""
    data = read_cast_result()
    if data and data.get("pending"):
        data.update(
            {
                "pending": False,
                "ok": False,
                "phase": "error",
                "error": "processo de cast interrompido",
                "message": "Transmissao anterior foi interrompida (app reiniciado).",
            }
        )
        write_cast_result(data)
        print("INFO: cast pendente orfao limpo na inicializacao", flush=True)


def _supervise_cast(proc: subprocess.Popen, device_label: str, timeout: float = CAST_JOB_TIMEOUT) -> None:
    """Garante que TODO cast termine com resultado final (nunca fica pendente)."""
    global _CAST_PROC
    killed = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        killed = True
        try:
            proc.kill()
        except Exception:
            pass
    finally:
        with _CAST_PROC_LOCK:
            if _CAST_PROC is proc:
                _CAST_PROC = None

    data = read_cast_result() or {}
    if not data.get("pending"):
        # worker ja escreveu o resultado final; so espelha no log do painel
        if data.get("ok"):
            cast_log(
                "success",
                data.get("message") or f"SUCCESS {data.get('device')}",
                ok=True,
                device=data.get("device"),
                url=data.get("url"),
                title=data.get("title"),
            )
        else:
            cast_log("error", data.get("message") or f"ERRO: {data.get('error')}", ok=False)
        return

    # worker morreu sem escrever: fecha o estado aqui
    if killed:
        err = f"tempo esgotado ({int(timeout)}s) falando com {device_label}"
    else:
        err = f"processo de cast terminou sem resposta (exit={proc.returncode})"
    data.update(
        {
            "pending": False,
            "ok": False,
            "phase": "error",
            "error": err,
            "message": f"ERRO: {err}",
        }
    )
    write_cast_result(data)
    cast_log("error", f"ERRO: {err}", ok=False)


def start_cast_job(
    url: str,
    title: str,
    host: str,
    name_hint: str,
    device_label: str,
    avt_control: str = "",
    dtype: str = "",
) -> dict:
    """Dispara o worker de cast em processo separado, com supervisor."""
    global _CAST_PROC, _LAST_RESULT_FINGERPRINT

    stop_cast_job(reason="novo cast solicitado", silent=True)

    worker = ROOT / "tools" / "cast_worker.py"
    payload_path = LOGS_DIR / "cast_payload.json"
    _LAST_RESULT_FINGERPRINT = ""

    payload = {
        "url": url,
        "title": title,
        "deviceName": name_hint,
        "host": host,
        "avt_control": avt_control,
        "type": dtype,
        "deviceLabel": device_label,
        "result_path": str(CAST_RESULT_PATH),
    }
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    write_cast_result(
        {
            "pending": True,
            "ok": None,
            "phase": "queued",
            "message": f"Preparando transmissao de '{title}' para {device_label}...",
            "url": url,
            "source_url": url,
            "title": title,
            "device": device_label,
            "deviceName": name_hint,
            "host": host,
            "started_at": _now_iso(),
        }
    )
    cast_log(
        "started",
        f"enviando comando cast: {title} -> {device_label}",
        ok=None,
        device=device_label,
        url=url,
        title=title,
    )
    try:
        chhealth.set_probe_paused(True)
    except Exception:
        pass

    proc = subprocess.Popen(
        [sys.executable, str(worker), str(payload_path)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with _CAST_PROC_LOCK:
        _CAST_PROC = proc
    threading.Thread(
        target=_supervise_cast,
        args=(proc, device_label),
        daemon=True,
        name="cast-supervisor",
    ).start()
    return {"pid": proc.pid}


def stop_cast_job(reason: str = "cancelado pelo usuario", silent: bool = False) -> bool:
    """Mata o worker em andamento e fecha o estado."""
    global _CAST_PROC
    with _CAST_PROC_LOCK:
        proc = _CAST_PROC
        _CAST_PROC = None
    stopped = False
    if proc is not None and proc.poll() is None:
        try:
            proc.kill()
            stopped = True
        except Exception:
            pass
    data = read_cast_result() or {}
    if data.get("pending"):
        data.update(
            {
                "pending": False,
                "ok": False,
                "phase": "error",
                "error": reason,
                "message": f"Transmissao interrompida: {reason}",
            }
        )
        write_cast_result(data)
        stopped = True
    if stopped and not silent:
        cast_log("error", f"cast interrompido: {reason}", ok=False)
    try:
        chhealth.set_probe_paused(False)
    except Exception:
        pass
    return stopped


class ApiHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        print(f"API: {self.address_string()} {fmt % args}", flush=True)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._json(
                200,
                {
                    "ok": True,
                    "ip": local_ip(),
                    "devices": len(DEVICES),
                    "cast": dict(CAST_STATE),
                    "pending": CAST_PENDING,
                },
            )
            return
        if path == "/devices":
            self._json(
                200,
                {
                    "devices": DEVICES,
                    "last_cast": LAST_CAST,
                    "cast": dict(CAST_STATE),
                    "pending": CAST_PENDING,
                },
            )
            return
        if path == "/cast_log":
            with _CAST_LOCK:
                logs = list(CAST_LOG[-80:])
                state = dict(CAST_STATE)
            self._json(200, {"logs": logs, "state": state, "pending": CAST_PENDING})
            return
        if path == "/channels":
            qs = parse_qs(urlparse(self.path).query)
            q = (qs.get("q") or [""])[0]
            playlist = (qs.get("playlist") or [""])[0]
            hide_dead = (qs.get("hide_dead") or ["0"])[0].lower() in ("1", "true", "yes")
            try:
                limit = int((qs.get("limit") or ["5000"])[0])
            except ValueError:
                limit = 5000
            reload_lists_catalog(force=False)
            if not q.strip() and not (playlist or "").strip():
                hits = get_ranked_channels(force=False)
                if hide_dead:
                    hits = [c for c in hits if not chhealth.should_hide(c, True)]
            else:
                raw_limit = min(30000, max(limit * 3, limit + 500)) if hide_dead else max(limit, 5000)
                hits = search_channels(q, limit=raw_limit, playlist_filter=playlist or None)
                hits = chhealth.attach_health_to_list(
                    hits,
                    hide_dead=hide_dead,
                    sort_by_signal=not bool(q.strip()),
                )
                if q.strip():
                    hits.sort(
                        key=lambda c: (
                            -int(c.get("score") or 0),
                            -int(c.get("signalStrength") or 0),
                            (c.get("name") or "").lower(),
                        )
                    )
            hits = hits[:limit]
            with _CATALOG_LOCK:
                ver = _CATALOG_VERSION
                folder = str(lists_folder())
            self._json(
                200,
                {
                    "query": q,
                    "playlist": playlist,
                    "count": len(hits),
                    "channels": hits,
                    "version": ver,
                    "folder": folder,
                    "hide_dead": hide_dead,
                    "health": chhealth.stats(),
                },
            )
            return
        if path == "/health_channels":
            self._json(200, chhealth.stats())
            return
        if path == "/probe/status":
            self._json(200, {"stats": chhealth.stats(), "probe": chhealth.probe_state()})
            return
        if path == "/playlists":
            reload_lists_catalog(force=False)
            with _CATALOG_LOCK:
                items = list(_CATALOG_PLAYLISTS)
                ver = _CATALOG_VERSION
                folder = str(lists_folder())
            if not items:
                db = Path.home() / ".iptvnator" / "databases" / "iptvnator.db"
                if db.exists():
                    conn = sqlite3.connect(str(db))
                    try:
                        for name, count, position in conn.execute(
                            "SELECT name, count, position FROM playlists ORDER BY position, name"
                        ):
                            items.append({"name": name, "count": count, "position": position})
                    finally:
                        conn.close()
            self._json(200, {"playlists": items, "version": ver, "folder": folder})
            return
        if path == "/catalog":
            info = reload_lists_catalog(force=False)
            self._json(200, info)
            return
        if path == "/catalog/reload":
            info = reload_lists_catalog(force=True)
            self._json(200, info)
            return
        if path == "/preview":
            qs = parse_qs(urlparse(self.path).query)
            url = (qs.get("url") or [""])[0]
            name = (qs.get("name") or [""])[0]
            self._json(200, probe_stream(url, name=name))
            return
        if path == "/proxy_media":
            qs = parse_qs(urlparse(self.path).query)
            url = (qs.get("url") or [""])[0].strip()
            if not url:
                self._json(400, {"error": "url vazia"})
                return
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "VLC/3.0.20 LibVLC/3.0.20",
                        "Accept": "*/*",
                    },
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    raw = resp.read()
                    ctype = (resp.headers.get("Content-Type") or "application/octet-stream").lower()
                    status = getattr(resp, "status", 200)
                looks_m3u = (
                    "#EXTM3U" in raw[:64].decode("utf-8", "replace")
                    or "mpegurl" in ctype
                    or url.lower().endswith((".m3u8", ".m3u"))
                )
                if looks_m3u:
                    text = raw.decode("utf-8", "replace")
                    body = proxy_rewrite_m3u(text, url)
                    ctype = "application/vnd.apple.mpegurl; charset=utf-8"
                else:
                    body = raw
                self.send_response(status if status < 400 else 200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except Exception as exc:  # noqa: BLE001
                self._json(502, {"error": f"proxy falhou: {exc}", "url": url})
            return
        if path == "/lookup":
            qs = parse_qs(urlparse(self.path).query)
            name = (qs.get("name") or [""])[0]
            hit = lookup_channel(name)
            if not hit:
                self._json(404, {"error": "canal nao encontrado", "name": name})
                return
            self._json(200, hit)
            return
        if path == "/scan":
            devices: list[dict] = []
            try:
                devices.extend(chromecast_scan(8.0))
            except Exception as exc:  # noqa: BLE001
                print("WARN chromecast_scan", exc, flush=True)
            try:
                raw = ssdp_search(3.0)
                devices.extend(enrich_devices(raw))
            except Exception as exc:  # noqa: BLE001
                print("WARN ssdp_scan", exc, flush=True)
            devices = normalize_devices(devices)
            DEVICES.clear()
            DEVICES.extend(devices)
            STATE_PATH.write_text(json.dumps(devices, ensure_ascii=False, indent=2), encoding="utf-8")
            castable = [d for d in devices if d.get("castable")]
            cast_log(
                "scan",
                f"scan OK: {len(devices)} dispositivo(s), {len(castable)} aceita(m) transmissao",
                ok=True,
                count=len(devices),
            )
            self._json(
                200,
                {
                    "count": len(devices),
                    "castable": len(castable),
                    "devices": devices,
                },
            )
            return
        if path == "/cast_status":
            global _LAST_RESULT_FINGERPRINT
            result_path = CAST_RESULT_PATH
            file_data: dict | None = None
            if result_path.exists():
                try:
                    raw = result_path.read_text(encoding="utf-8")
                    file_data = json.loads(raw)
                    fp = raw
                except Exception as exc:  # noqa: BLE001
                    file_data = {"error": f"result ilegivel: {exc}", "pending": False}
                    fp = str(file_data)
            else:
                fp = ""
            if file_data and not file_data.get("pending") and fp and fp != _LAST_RESULT_FINGERPRINT:
                _LAST_RESULT_FINGERPRINT = fp
                if file_data.get("ok"):
                    cast_log(
                        "success",
                        file_data.get("message")
                        or f"SUCCESS {file_data.get('device')} player={file_data.get('player')}",
                        ok=True,
                        device=file_data.get("device"),
                        url=file_data.get("url"),
                        player=file_data.get("player"),
                    )
                    try:
                        src = file_data.get("source_url") or file_data.get("url") or ""
                        play = file_data.get("url") or ""
                        title = file_data.get("title") or ""
                        chhealth.mark_confirmed(src, name=title)
                        if play and play != src:
                            chhealth.mark_confirmed(play, name=title)
                    except Exception as exc:  # noqa: BLE001
                        print("WARN mark_confirmed:", exc, flush=True)
                    try:
                        chhealth.set_probe_paused(False)
                    except Exception:
                        pass
                elif file_data.get("error") or file_data.get("ok") is False:
                    cast_log(
                        "error",
                        file_data.get("message") or f"ERRO: {file_data.get('error')}",
                        ok=False,
                    )
                    try:
                        chhealth.mark_cast_fail(
                            file_data.get("url") or file_data.get("source_url") or "",
                            error=file_data.get("error") or file_data.get("message") or "",
                            name=file_data.get("title") or "",
                        )
                        chhealth.save_health()
                    except Exception:
                        pass
                    try:
                        chhealth.set_probe_paused(False)
                    except Exception:
                        pass
            with _CAST_LOCK:
                state = dict(CAST_STATE)
                logs = list(CAST_LOG[-30:])
                pending = CAST_PENDING
            out = {
                "pending": bool(file_data.get("pending")) if file_data else pending,
                "state": state,
                "logs": logs,
            }
            if file_data:
                out.update(file_data)
                if "pending" not in file_data:
                    out["pending"] = pending
            self._json(200, out)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            data = {}
        if path == "/cast":
            try:
                url = data.get("url") or ""
                title = data.get("title") or "IPTV"
                host = (data.get("host") or "").strip()
                name_hint = (data.get("deviceName") or host or "philips").lower()
                channel_name = data.get("channelName") or title
                if not url and channel_name:
                    hit = lookup_channel(channel_name)
                    if hit:
                        url = hit["url"]
                        title = hit["name"]
                if not url:
                    url = GLOBO_RJ
                    title = title or "TV Globo RJ"

                # resolve o dispositivo real da lista descoberta
                device = find_device(host) or find_device(name_hint)
                if device:
                    host = device.get("host") or host
                    avt_control = device.get("avt_control") or ""
                    dtype = device.get("type") or ""
                    device_label = data.get("deviceLabel") or (
                        f"{device.get('friendlyName') or host} @ {host}" if host else name_hint
                    )
                else:
                    avt_control = (data.get("avt_control") or "").strip()
                    dtype = (data.get("type") or "").strip()
                    device_label = data.get("deviceLabel") or name_hint

                # nao deixa mandar cast pra roteador/WPS (erro claro em vez de silencio)
                if device and not device_is_castable(device):
                    msg = (
                        f"'{device.get('friendlyName') or host}' nao aceita transmissao "
                        "(nao e TV/Chromecast). Ligue a TV e clique em 'Procurar TVs'."
                    )
                    cast_log("error", msg, ok=False)
                    self._json(
                        400,
                        {
                            "ok": False,
                            "started": False,
                            "pending": False,
                            "error": msg,
                            "message": msg,
                            "hint": "device_not_castable",
                        },
                    )
                    return

                job = start_cast_job(
                    url=url,
                    title=title,
                    host=host,
                    name_hint=name_hint,
                    device_label=device_label,
                    avt_control=avt_control,
                    dtype=dtype,
                )
                self._json(
                    200,
                    {
                        "ok": True,
                        "started": True,
                        "pending": True,
                        "device": device_label,
                        "host": host,
                        "url": url,
                        "title": title,
                        "pid": job.get("pid"),
                        "message": "cast iniciado; acompanhe o status no painel",
                        "state": dict(CAST_STATE),
                    },
                )
            except Exception as exc:  # noqa: BLE001
                print("ERRO /cast", exc, flush=True)
                cast_log("error", f"ERRO ao iniciar cast: {exc}", ok=False)
                write_cast_result(
                    {
                        "pending": False,
                        "ok": False,
                        "phase": "error",
                        "error": str(exc),
                        "message": f"ERRO ao iniciar cast: {exc}",
                    }
                )
                self._json(500, {"ok": False, "error": str(exc), "message": f"ERRO: {exc}"})
            return
        if path in ("/cast/stop", "/cast/cancel"):
            stopped = stop_cast_job(reason=data.get("reason") or "cancelado pelo usuario")
            self._json(200, {"ok": True, "stopped": stopped, "pending": False})
            return
        if path == "/play":
            url = (data.get("url") or "").strip()
            title = data.get("title") or data.get("channelName") or "IPTV"
            if not url and data.get("channelName"):
                hit = lookup_channel(str(data.get("channelName")))
                if hit:
                    url = hit["url"]
                    title = hit["name"]
            result = play_in_mpv(url, title=str(title))
            code = 200 if result.get("ok") else 500
            self._json(code, result)
            return
        if path == "/probe/batch":
            items = data.get("channels") or data.get("items") or []
            if not items and data.get("urls"):
                items = [{"url": u} for u in data.get("urls") or []]
            if not items:
                # se vazio, pega amostra do catalogo
                q = (data.get("q") or "").strip()
                playlist = (data.get("playlist") or "").strip() or None
                limit = int(data.get("limit") or 40)
                items = search_channels(q, limit=limit, playlist_filter=playlist)
            workers = int(data.get("workers") or 6)
            if chhealth.probe_state().get("running"):
                self._json(409, {"error": "probe ja em andamento", "probe": chhealth.probe_state()})
                return

            def work() -> None:
                chhealth.run_batch_probe(
                    items,
                    probe_fn=lambda u: probe_stream(u, timeout=7.0, update_health=False),
                    workers=workers,
                    save_every=15,
                )

            threading.Thread(target=work, daemon=True, name="probe-batch").start()
            self._json(200, {"ok": True, "started": True, "queued": len(items)})
            return
        self._json(404, {"error": "not found"})


def start_api() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", API_PORT), ApiHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def background_device_scan(interval: float = 90.0) -> None:
    def loop() -> None:
        while True:
            try:
                devices: list[dict] = []
                try:
                    devices.extend(chromecast_scan(8.0))
                except Exception as exc:  # noqa: BLE001
                    print("WARN auto chromecast_scan", exc, flush=True)
                try:
                    devices.extend(enrich_devices(ssdp_search(2.5)))
                except Exception:
                    pass
                devices = normalize_devices(devices)
                if devices:
                    DEVICES.clear()
                    DEVICES.extend(devices)
                    STATE_PATH.write_text(json.dumps(devices, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"INFO: auto-scan {len(devices)} device(s)", flush=True)
            except Exception as exc:  # noqa: BLE001
                print("WARN auto-scan", exc, flush=True)
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True, name="auto-scan").start()


INJECT_JS = r"""
(() => {
  const VERSION = 17;
  const API = 'http://127.0.0.1:8769';
  // remove overlay antigo (cast agora e janela externa grudada)
  const oldPanel = document.getElementById('iptv-debug-panel');
  if (oldPanel) oldPanel.remove();
  const oldFab = document.getElementById('iptv-companion-fab');
  if (oldFab) oldFab.remove();
  const oldStyle = document.getElementById('iptv-companion-style');
  if (oldStyle) oldStyle.remove();
  if (window.__iptvCompanionVersion === VERSION && window.__iptvPlayHookedV17) {
    return { already: true, version: VERSION, mode: 'external-dock' };
  }
  window.__iptvCompanionVersion = VERSION;

  async function forcePlayerSettings() {
    try {
      const mpv = 'C:\\\\Program Files\\\\MPV Player\\\\mpv.exe';
      const vlc = 'C:\\\\Program Files\\\\VideoLAN\\\\VLC\\\\vlc.exe';
      await window.electron.setMpvPlayerPath(mpv);
      await window.electron.setVlcPlayerPath(vlc);
      await window.electron.updateSettings({
        player: 'mpv',
        mpvPlayerPath: mpv,
        vlcPlayerPath: vlc,
        mpvReuseInstance: true,
        vlcReuseInstance: true,
        mpvPlayerArguments: '--hwdec=auto --cache=yes --demuxer-max-bytes=64M --force-window=yes',
        showExternalPlaybackBar: true,
      });
      return 'mpv';
    } catch (e) {
      return 'err:' + e;
    }
  }

  async function openMpv(url, title) {
    if (!url) return null;
    return await window.electron.openInMpv(url, title || 'IPTV', '', 'VLC/3.0.20 LibVLC/3.0.20', '', '');
  }

  if (!window.__iptvPlayHookedV17) {
    window.__iptvPlayHookedV17 = true;
    document.addEventListener('click', (ev) => {
      const el = ev.target && ev.target.closest && ev.target.closest('button,a,div,li,mat-list-item,.channel-item');
      if (!el) return;
      let t = (el.textContent || '').replace(/\\s+/g, ' ').trim();
      t = t.replace(/No program information available.*/i, '').replace(/star_outline|favorite|chevron.*/ig, '').trim();
      if (t.length < 3 || t.length > 100) return;
      if (/Open in|Retry|COPY|Scan|Espelhar|Settings|dashboard|playlist_play|Recently|Filter|TIMELINE|volume|fullscreen|Cast|ABRIR|FECHAR/i.test(t)) return;
      const channelName = t.split('  ')[0].trim();
      setTimeout(async () => {
        try {
          const r = await fetch(API + '/lookup?name=' + encodeURIComponent(channelName));
          if (!r.ok) return;
          const hit = await r.json();
          await openMpv(hit.url, hit.name);
        } catch (e) {}
      }, 200);
    }, true);
  }

  forcePlayerSettings();
  return { installed: true, version: VERSION, mode: 'external-dock' };
})()
"""


def homedir() -> Path:
    return Path.home()


def iptvnator_exe() -> Path:
    return homedir() / "AppData" / "Local" / "Programs" / "iptvnator" / "IPTVnator.exe"


def ensure_config() -> None:
    cfg_path = homedir() / "AppData" / "Roaming" / "iptvnator" / "config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    cfg["MPV_PLAYER_PATH"] = str(Path(r"C:\Program Files\MPV Player\mpv.exe"))
    cfg["VLC_PLAYER_PATH"] = str(Path(r"C:\Program Files\VideoLAN\VLC\vlc.exe"))
    cfg["MPV_REUSE_INSTANCE"] = True
    cfg["VLC_REUSE_INSTANCE"] = True
    cfg["MPV_PLAYER_ARGUMENTS"] = "--hwdec=auto --cache=yes --demuxer-max-bytes=64M --force-window=yes"
    cfg_path.write_text(json.dumps(cfg, indent="\t", ensure_ascii=False) + "\n", encoding="utf-8")


def kill_iptvnator(also_mpv: bool = False) -> None:
    subprocess.run(["taskkill", "/IM", "IPTVnator.exe", "/F"], capture_output=True, check=False)
    if also_mpv:
        subprocess.run(["taskkill", "/IM", "mpv.exe", "/F"], capture_output=True, check=False)
    time.sleep(1.2)


def start_iptvnator() -> subprocess.Popen:
    flags = 0x00000008  # DETACHED_PROCESS
    return subprocess.Popen(
        [str(iptvnator_exe()), f"--remote-debugging-port={CDP_PORT}"],
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_cdp(timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=2) as resp:
                targets = json.loads(resp.read().decode())
            page = next(t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl"))
            return page
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.4)
    raise TimeoutError(str(last))


async def cdp_eval(ws, expr: str, msg_id: int) -> dict:
    await ws.send(
        json.dumps(
            {
                "id": msg_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expr,
                    "awaitPromise": True,
                    "returnByValue": True,
                    "userFacing": True,
                },
            }
        )
    )
    while True:
        raw = json.loads(await ws.recv())
        if raw.get("id") == msg_id:
            return raw


async def inject_loop(page: dict) -> None:
    msg_id = 1
    while True:
        try:
            async with websockets.connect(page["webSocketDebuggerUrl"], max_size=4_000_000) as ws:
                while True:
                    msg_id += 1
                    r = await cdp_eval(ws, INJECT_JS, msg_id)
                    val = ((r.get("result") or {}).get("result") or {}).get("value")
                    if msg_id % 10 == 0:
                        print(f"INFO: inject {val}", flush=True)
                    await asyncio.sleep(2.5)
        except Exception as exc:  # noqa: BLE001
            print(f"INFO: cdp reconnect ({exc})", flush=True)
            await asyncio.sleep(1.5)
            try:
                page = wait_cdp(15)
            except Exception:
                continue



def free_port(port: int) -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
                "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
            ),
        ],
        capture_output=True,
        check=False,
    )


def ensure_frontend_dist() -> bool:
    """Garante build do React em frontend/dist."""
    index = FRONTEND_DIST / "index.html"
    need_build = not index.exists()
    if index.exists():
        idx_mtime = index.stat().st_mtime
        src_dir = FRONTEND_DIR / "src"
        if src_dir.exists():
            for p in src_dir.rglob("*"):
                if p.is_file() and p.stat().st_mtime > idx_mtime:
                    need_build = True
                    break
        pkg_file = FRONTEND_DIR / "package.json"
        if pkg_file.exists() and pkg_file.stat().st_mtime > idx_mtime:
            need_build = True
    if not need_build:
        return True
    pkg = FRONTEND_DIR / "package.json"
    if not pkg.exists():
        print("WARN: frontend ausente em", FRONTEND_DIR, flush=True)
        return False
    npm = "npm.cmd" if sys.platform.startswith("win") else "npm"
    print("INFO: gerando build do frontend...", flush=True)
    if not (FRONTEND_DIR / "node_modules").exists():
        r = subprocess.run([npm, "install"], cwd=str(FRONTEND_DIR), capture_output=True, text=True)
        if r.returncode != 0:
            print("ERRO npm install:", (r.stderr or r.stdout)[:400], flush=True)
            return False
    r = subprocess.run([npm, "run", "build"], cwd=str(FRONTEND_DIR), capture_output=True, text=True)
    if r.returncode != 0 or not index.exists():
        print("ERRO npm build:", (r.stderr or r.stdout)[:400], flush=True)
        return False
    print("OK: frontend build pronto", flush=True)
    return True


class FrontendHandler(SimpleHTTPRequestHandler):
    """Serve o SPA React (dist) na porta 3000."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIST), **kwargs)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        file_path = FRONTEND_DIST / path.lstrip("/")
        if path == "/" or not file_path.exists() or file_path.is_dir():
            # SPA fallback
            if path != "/" and "." in Path(path).name:
                return super().do_GET()
            self.path = "/index.html"
        return super().do_GET()


def start_frontend_ui(open_browser: bool = True) -> bool:
    """Sobe o front web e abre no navegador (substitui o dock Tk como UI principal)."""
    want_browser = bool(open_browser) and browser_should_open()
    if frontend_is_up():
        print("OK: frontend ja estava no ar", flush=True)
        if want_browser:
            open_frontend_tab()
        return True
    if not ensure_frontend_dist():
        return False
    free_port(FRONTEND_PORT)

    def serve() -> None:
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", FRONTEND_PORT), FrontendHandler)
            print(f"OK: frontend em http://127.0.0.1:{FRONTEND_PORT}", flush=True)
            httpd.serve_forever()
        except Exception as exc:  # noqa: BLE001
            print("ERRO frontend server:", exc, flush=True)

    threading.Thread(target=serve, daemon=True, name="frontend-ui").start()
    time.sleep(0.4)
    if want_browser:
        open_frontend_tab()
    return True


def api_is_up() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{API_PORT}/health", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return bool(data.get("ok"))
    except Exception:
        return False


def frontend_is_up() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{FRONTEND_PORT}/", timeout=2) as resp:
            return int(getattr(resp, "status", 200) or 200) < 500
    except Exception:
        return False


def chrome_exe() -> Path | None:
    import os

    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"
    candidates = [
        pf / "Google" / "Chrome" / "Application" / "chrome.exe",
        pf86 / "Google" / "Chrome" / "Application" / "chrome.exe",
        local,
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def browser_should_open() -> bool:
    """Launcher gerenciado (iniciar_iptv_app.py) abre o Chrome; companion nao abre sozinho."""
    return (__import__("os").environ.get("IPTV_NO_BROWSER") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
    )


def open_frontend_tab() -> None:
    """Abre o Chrome em modo App na UI web."""
    if not browser_should_open():
        print("INFO: IPTV_NO_BROWSER=1 - Chrome fica a cargo do launcher", flush=True)
        return
    url = f"http://127.0.0.1:{FRONTEND_PORT}/"
    chrome = chrome_exe()
    if chrome:
        try:
            profile_dir = ROOT / "chrome-app-profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(
                [
                    str(chrome),
                    f"--user-data-dir={profile_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    f"--app={url}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print("OK: Chrome App ->", url, flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            print("WARN: falha ao abrir Chrome:", exc, flush=True)
    try:
        webbrowser.open(url)
        print("OK: navegador padrao ->", url, flush=True)
    except Exception as exc:  # noqa: BLE001
        print("WARN: navegador:", exc, "->", url, flush=True)


_RANKED_CACHE: list[dict] = []
_RANKED_CACHE_AT = 0.0
_RANKED_CACHE_LOCK = threading.Lock()
_RANKED_TTL = 45.0


def get_ranked_channels(force: bool = False) -> list[dict]:
    """Cache da lista ordenada por sinal (evita reprocessar 17k a cada F5)."""
    global _RANKED_CACHE, _RANKED_CACHE_AT
    now = time.time()
    with _RANKED_CACHE_LOCK:
        if not force and _RANKED_CACHE and (now - _RANKED_CACHE_AT) < _RANKED_TTL:
            return list(_RANKED_CACHE)
    reload_lists_catalog(force=False)
    raw = search_channels("", limit=30000, playlist_filter=None)
    ranked = chhealth.attach_health_to_list(raw, hide_dead=False, sort_by_signal=True)
    with _RANKED_CACHE_LOCK:
        _RANKED_CACHE = ranked
        _RANKED_CACHE_AT = time.time()
        return list(ranked)


def invalidate_ranked_cache() -> None:
    global _RANKED_CACHE_AT
    with _RANKED_CACHE_LOCK:
        _RANKED_CACHE_AT = 0.0


def kill_dock_window() -> None:
    """Encerra qualquer janela de Dock Tkinter legada."""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'cast_dock_window\\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
            capture_output=True,
            check=False,
        )
    except Exception:
        pass


def start_cast_dock() -> None:
    """Sem janela dock Tkinter - limpo."""
    kill_dock_window()


def main() -> int:
    kill_dock_window()

    # libera portas de sessoes anteriores
    if api_is_up() or frontend_is_up():
        print("INFO: liberando portas 8769 e 3000...", flush=True)
        free_port(API_PORT)
        free_port(FRONTEND_PORT)
        time.sleep(0.5)

    # evita instancias duplicadas
    pid_path = LOGS_DIR / "companion.pid"
    if pid_path.exists():
        try:
            old = int(pid_path.read_text(encoding="utf-8").strip())
            subprocess.run(["taskkill", "/PID", str(old), "/F"], capture_output=True, check=False)
        except Exception:
            pass

    print("INFO: IP local=", local_ip(), flush=True)

    # cast pendente orfao da sessao anterior nao pode travar a UI
    clear_stale_cast_pending()

    # devices conhecidos ficam disponiveis ja no primeiro /devices (antes do scan)
    try:
        if STATE_PATH.exists():
            cached = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(cached, list) and cached:
                DEVICES.clear()
                DEVICES.extend(normalize_devices(cached))
                print(f"INFO: {len(DEVICES)} dispositivo(s) carregados do cache", flush=True)
    except Exception as exc:  # noqa: BLE001
        print("WARN cache de devices:", exc, flush=True)

    ensure_config()
    folder = lists_folder()
    cfg = ROOT / "lists_folder.txt"
    if not cfg.exists():
        cfg.write_text(str(folder) + "\n", encoding="utf-8")
    readme = folder / "LEIA-ME-LISTAS.txt"
    if not readme.exists():
        readme.write_text(
            "Coloque aqui arquivos .m3u / .m3u8\n"
            "O Cast Companion detecta sozinho quando voce adiciona, remove ou altera listas.\n"
            "Nao precisa fechar o programa.\n"
            "Para mudar a pasta, edite: Documents\\iptv-org-test\\lists_folder.txt\n",
            encoding="utf-8",
        )
    print("INFO: subindo API DLNA :", API_PORT, flush=True)
    try:
        start_api()
    except OSError as exc:
        print("ERRO: porta 8769 ocupada, tentando liberar...", exc, flush=True)
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Get-NetTCPConnection -LocalPort 8769 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"],
                       check=False)
        time.sleep(1)
        start_api()
    pid_path.write_text(str(__import__("os").getpid()), encoding="utf-8")

    # 1. Carrega catalogo e monitora listas em segundo plano
    def _bg_catalog():
        folder = lists_folder()
        print("INFO: pasta de listas M3U =", folder, flush=True)
        reload_lists_catalog(force=True)
        background_lists_watch(2.0)
        chhealth.load_health()

    threading.Thread(target=_bg_catalog, daemon=True).start()

    # 2. Procura TVs sozinho (a TV so aparece quando sai do standby)
    background_device_scan(120.0)

    # 3. Sobe o Frontend Web (porta 3000) e abre diretamente no Chrome
    start_frontend_ui(open_browser=True)

    print("OK: IPTV Cast Companion ativo (API :8769 + Chrome :3000)", flush=True)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("INFO: stop", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
