#!/usr/bin/env python3
"""Inicia o IPTVnator com fallback automatico + painel Copy error logs."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

DEPENDENCIAS = ["websockets"]


def garantir_dependencias() -> None:
    import importlib.util

    faltando = [d for d in DEPENDENCIAS if importlib.util.find_spec(d) is None]
    if not faltando:
        return
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", *faltando],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


garantir_dependencias()
import websockets  # noqa: E402

CDP_PORT = 9222
GLOBO_RJ = "http://45.190.28.50/GLOBO_HD/index.m3u8"

INJECT_JS = r"""
(() => {
  const VERSION = 3;
  const GLOBO_RJ = "http://45.190.28.50/GLOBO_HD/index.m3u8";
  if (window.__iptvAutoFallbackVersion === VERSION && document.getElementById('iptv-debug-panel') && document.getElementById('iptv-copy-error-logs-btn')) {
    return { already: true, version: VERSION };
  }
  window.__iptvAutoFallbackVersion = VERSION;
  window.__iptvAutoFallbackInstalled = true;
  window.__iptvAutoFallbackState = window.__iptvAutoFallbackState || {
    lastKey: null, tried: [], channelSkips: 0, lastActionAt: 0,
  };
  window.__iptvErrorLogBuffer = window.__iptvErrorLogBuffer || [];

  if (!window.__iptvConsoleHooked) {
    window.__iptvConsoleHooked = true;
    ['error','warn','info','log'].forEach((level) => {
      const orig = console[level].bind(console);
      console[level] = (...args) => {
        try {
          const msg = args.map(a => a instanceof Error ? (a.stack||a.message) : (typeof a==='object'?JSON.stringify(a):String(a))).join(' ');
          window.__iptvErrorLogBuffer.push({ts:new Date().toISOString(), level, message: msg});
          if (window.__iptvErrorLogBuffer.length > 400) window.__iptvErrorLogBuffer.shift();
        } catch (e) {}
        orig(...args);
      };
    });
    window.addEventListener('error', (ev) => {
      window.__iptvErrorLogBuffer.push({ts:new Date().toISOString(), level:'window.onerror', message: `${ev.message}\n${ev.error && ev.error.stack || ''}`});
    });
    window.addEventListener('unhandledrejection', (ev) => {
      const r = ev.reason;
      window.__iptvErrorLogBuffer.push({ts:new Date().toISOString(), level:'unhandledrejection', message: r instanceof Error ? (r.stack||r.message) : String(r)});
    });
  }

  function ensurePanel() {
    let panel = document.getElementById('iptv-debug-panel');
    if (panel && !document.getElementById('iptv-copy-error-logs-btn')) {
      panel.remove();
      panel = null;
    }
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'iptv-debug-panel';
      panel.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:2147483647;width:310px;background:#111;color:#fff;border:2px solid #ffc107;border-radius:10px;padding:10px;font:12px/1.35 Segoe UI,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.5)';
      panel.innerHTML = `
        <div style="font-weight:700;color:#ffc107;margin-bottom:6px">IPTV Debug</div>
        <div id="iptv-debug-status" style="margin-bottom:8px;color:#ffe082">painel ativo</div>
        <button id="iptv-copy-error-logs-btn" style="width:100%;padding:10px;margin-bottom:6px;border:0;border-radius:8px;background:#ffc107;color:#111;font-weight:700;cursor:pointer">Copy error logs</button>
        <button id="iptv-play-globo-rj" style="width:100%;padding:8px;margin-bottom:6px;border:0;border-radius:8px;background:#2e7d32;color:#fff;font-weight:700;cursor:pointer">Play TV Globo RJ (MPV)</button>
        <button id="iptv-open-mpv-btn" style="width:100%;padding:8px;margin-bottom:6px;border:0;border-radius:8px;background:#333;color:#fff;cursor:pointer">Open current in MPV</button>
        <button id="iptv-open-vlc-btn" style="width:100%;padding:8px;border:0;border-radius:8px;background:#333;color:#fff;cursor:pointer">Open current in VLC</button>
      `;
      document.documentElement.appendChild(panel);

      document.getElementById('iptv-copy-error-logs-btn').onclick = async () => {
        const ok = await copyText(buildReport());
        const b = document.getElementById('iptv-copy-error-logs-btn');
        b.textContent = ok ? 'COPIADO!' : 'FALHOU';
        b.style.background = ok ? '#1b5e20' : '#b71c1c';
        b.style.color = '#fff';
        setTimeout(() => { b.textContent = 'Copy error logs'; b.style.background = '#ffc107'; b.style.color = '#111'; }, 1600);
      };
      document.getElementById('iptv-play-globo-rj').onclick = async () => {
        try {
          await window.electron.openInMpv(GLOBO_RJ, 'TV Globo RJ', '', 'VLC/3.0.20 LibVLC/3.0.20', '', '');
          setStatus('MPV: TV Globo RJ', '#a5d6a7');
        } catch (e) { setStatus('erro: ' + e, '#ff8a80'); }
      };
      document.getElementById('iptv-open-mpv-btn').onclick = () => clickBy(/Open in MPV/i);
      document.getElementById('iptv-open-vlc-btn').onclick = () => clickBy(/Open in VLC/i);
    }
    const t = document.body && document.body.innerText || '';
    const failed = /loading failed|UNSUPPORTED|could not be loaded|Open it in a native player/i.test(t);
    setStatus(failed ? 'ERRO de playback - use Copy error logs / MPV' : 'painel ativo', failed ? '#ff8a80' : '#ffe082');
  }

  function setStatus(msg, color) {
    const el = document.getElementById('iptv-debug-status');
    if (!el) return;
    el.textContent = msg;
    if (color) el.style.color = color;
  }

  function buildReport() {
    const logs = (window.__iptvErrorLogBuffer||[]).slice(-150);
    const urls = [];
    document.querySelectorAll('video').forEach(v => { if (v.src) urls.push(v.src); if (v.currentSrc) urls.push(v.currentSrc); });
    return [
      '=== IPTVnator error report ===',
      'timestamp: ' + new Date().toISOString(),
      'href: ' + location.href,
      'note: Rede Globo da lista publica costuma estar morta. TV Globo RJ: ' + GLOBO_RJ,
      '',
      '=== page text ===',
      (document.body.innerText||'').slice(0,6000),
      '',
      '=== urls ===',
      ...(urls.length ? urls : ['(none)']),
      '',
      '=== console/traceback ===',
      ...(logs.length ? logs.map(l => `[${l.ts}] ${l.level}: ${l.message}`) : ['(vazio)']),
      '',
      '=== end ==='
    ].join('\n');
  }

  async function copyText(t) {
    try { await navigator.clipboard.writeText(t); return true; }
    catch (e) {
      const ta = document.createElement('textarea');
      ta.value = t; document.body.appendChild(ta); ta.select();
      const ok = document.execCommand('copy'); ta.remove(); return ok;
    }
  }

  function clickBy(re) {
    const b = [...document.querySelectorAll('button,a,[role=button]')].find(x => re.test((x.innerText||'').replace(/\s+/g,' ')));
    if (b) { b.click(); return true; }
    return false;
  }

  function diagnosticVisible() {
    const t = document.body && document.body.innerText || '';
    return /UNSUPPORTED|Open it in a native player|could not be loaded|loading failed/i.test(t);
  }

  function currentChannelKey() {
    return (location.href + '|' + (document.body.innerText||'').slice(0,200));
  }

  async function tick() {
    ensurePanel();
    if (!diagnosticVisible()) {
      const st = window.__iptvAutoFallbackState;
      if (st.lastKey && Date.now() - st.lastActionAt > 8000) { st.tried = []; st.channelSkips = 0; }
      return;
    }
    const st = window.__iptvAutoFallbackState;
    const key = currentChannelKey();
    if (st.lastKey !== key) { st.lastKey = key; st.tried = []; st.channelSkips = 0; }
    if (Date.now() - st.lastActionAt < 2500) return;

    if (!st.tried.includes('mpv')) {
      st.tried.push('mpv'); st.lastActionAt = Date.now();
      if (!clickBy(/Open in MPV/i)) {
        // tenta abrir URL do video se houver
        const v = document.querySelector('video');
        const url = (v && (v.currentSrc || v.src)) || '';
        if (url && window.electron?.openInMpv) {
          try { await window.electron.openInMpv(url, 'stream', '', 'VLC/3.0.20 LibVLC/3.0.20', '', ''); } catch (e) {}
        }
      }
      return;
    }
    if (!st.tried.includes('vlc')) {
      st.tried.push('vlc'); st.lastActionAt = Date.now();
      clickBy(/Open in VLC/i);
      return;
    }
  }

  if (window.__iptvAutoFallbackTimer) clearInterval(window.__iptvAutoFallbackTimer);
  window.__iptvAutoFallbackTimer = setInterval(() => { tick().catch(() => {}); }, 1000);
  tick().catch(() => {});
  return { installed: true, version: VERSION, panel: !!document.getElementById('iptv-debug-panel'), copy: !!document.getElementById('iptv-copy-error-logs-btn') };
})()
"""


def homedir() -> Path:
    return Path.home()


def iptvnator_exe() -> Path:
    return homedir() / "AppData" / "Local" / "Programs" / "iptvnator" / "IPTVnator.exe"


def ensure_config() -> None:
    cfg_path = homedir() / "AppData" / "Roaming" / "iptvnator" / "config.json"
    mpv = Path(r"C:\Program Files\MPV Player\mpv.exe")
    vlc = Path(r"C:\Program Files\VideoLAN\VLC\vlc.exe")
    cfg = {}
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["MPV_PLAYER_PATH"] = str(mpv)
    cfg["VLC_PLAYER_PATH"] = str(vlc)
    cfg["MPV_REUSE_INSTANCE"] = True
    cfg["VLC_REUSE_INSTANCE"] = True
    cfg["MPV_PLAYER_ARGUMENTS"] = "--hwdec=auto --cache=yes --demuxer-max-bytes=64M"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, indent="\t", ensure_ascii=False) + "\n", encoding="utf-8")


def kill_iptvnator() -> None:
    subprocess.run(["taskkill", "/IM", "IPTVnator.exe", "/F"], capture_output=True, check=False)
    time.sleep(1.2)


def start_iptvnator() -> subprocess.Popen:
    exe = iptvnator_exe()
    if not exe.exists():
        raise FileNotFoundError(str(exe))
    return subprocess.Popen(
        [str(exe), f"--remote-debugging-port={CDP_PORT}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_cdp(timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=2) as resp:
                targets = json.loads(resp.read().decode("utf-8"))
            page = next((t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")), None)
            if page:
                return page
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(0.5)
    raise TimeoutError(str(last_err))


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
    msg_id = 10
    fail_streak = 0
    while True:
        try:
            async with websockets.connect(page["webSocketDebuggerUrl"], max_size=4_000_000) as ws:
                while True:
                    msg_id += 1
                    result = await cdp_eval(ws, INJECT_JS, msg_id)
                    val = ((result.get("result") or {}).get("result") or {}).get("value")
                    if msg_id % 15 == 0:
                        print(f"INFO: inject {val}", flush=True)
                    fail_streak = 0
                    await asyncio.sleep(2.5)
        except Exception as exc:  # noqa: BLE001
            fail_streak += 1
            print(f"INFO: reconectando CDP ({exc})", flush=True)
            await asyncio.sleep(1.5)
            try:
                page = wait_cdp(timeout=15)
            except Exception:
                if fail_streak > 20:
                    print("ERRO: CDP perdido", flush=True)
                    return


def main() -> int:
    print("INFO: config players...", flush=True)
    ensure_config()
    print("INFO: reiniciando IPTVnator...", flush=True)
    kill_iptvnator()
    proc = start_iptvnator()
    print(f"INFO: pid={proc.pid}", flush=True)
    page = wait_cdp()
    print("OK: painel Copy error logs + fallback ativos", flush=True)
    try:
        asyncio.run(inject_loop(page))
    except KeyboardInterrupt:
        print("INFO: parado", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
