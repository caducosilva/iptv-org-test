#!/usr/bin/env python3
"""Forca painel de debug com Copy logs e abre TV Globo RJ no MPV."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import urllib.request

try:
    import websockets
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "websockets"])
    import websockets

GLOBO_RJ = "http://45.190.28.50/GLOBO_HD/index.m3u8"

PANEL_JS = r"""
(async () => {
  const GLOBO_RJ = "http://45.190.28.50/GLOBO_HD/index.m3u8";
  // remove painel velho incompleto
  const old = document.getElementById('iptv-debug-panel');
  if (old) old.remove();

  const panel = document.createElement('div');
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

  function buildReport() {
    const logs = (window.__iptvErrorLogBuffer||[]).slice(-150);
    const urls = [];
    document.querySelectorAll('video').forEach(v => { if (v.src) urls.push(v.src); if (v.currentSrc) urls.push(v.currentSrc); });
    const deadNote = 'Rede Globo (cors-proxy) esta morta. Use TV Globo Rio de Janeiro: ' + GLOBO_RJ;
    return [
      '=== IPTVnator error report ===',
      'timestamp: ' + new Date().toISOString(),
      'href: ' + location.href,
      deadNote,
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

  document.getElementById('iptv-copy-error-logs-btn').onclick = async () => {
    const ok = await copyText(buildReport());
    const b = document.getElementById('iptv-copy-error-logs-btn');
    b.textContent = ok ? 'COPIADO!' : 'FALHOU';
    b.style.background = ok ? '#1b5e20' : '#b71c1c';
    b.style.color = '#fff';
    setTimeout(() => {
      b.textContent = 'Copy error logs';
      b.style.background = '#ffc107';
      b.style.color = '#111';
    }, 1600);
  };

  document.getElementById('iptv-play-globo-rj').onclick = async () => {
    const st = document.getElementById('iptv-debug-status');
    try {
      await window.electron.openInMpv(GLOBO_RJ, 'TV Globo RJ', '', 'VLC/3.0.20 LibVLC/3.0.20', '', '');
      st.textContent = 'MPV: TV Globo RJ';
      st.style.color = '#a5d6a7';
    } catch (e) {
      st.textContent = 'erro openInMpv: ' + e;
      st.style.color = '#ff8a80';
    }
  };

  const clickBy = (re) => {
    const b = [...document.querySelectorAll('button')].find(x => re.test(x.innerText||''));
    if (b) b.click();
  };
  document.getElementById('iptv-open-mpv-btn').onclick = () => clickBy(/Open in MPV/i);
  document.getElementById('iptv-open-vlc-btn').onclick = () => clickBy(/Open in VLC/i);

  // abre Globo RJ agora
  let openResult = null;
  try {
    openResult = await window.electron.openInMpv(GLOBO_RJ, 'TV Globo RJ', '', 'VLC/3.0.20 LibVLC/3.0.20', '', '');
    document.getElementById('iptv-debug-status').textContent = 'Rede Globo da lista esta morta. Abrindo TV Globo RJ no MPV.';
    document.getElementById('iptv-debug-status').style.color = '#a5d6a7';
  } catch (e) {
    openResult = String(e);
    document.getElementById('iptv-debug-status').textContent = 'falha MPV: ' + e;
    document.getElementById('iptv-debug-status').style.color = '#ff8a80';
  }

  return {
    panel: true,
    hasCopyBtn: !!document.getElementById('iptv-copy-error-logs-btn'),
    openResult,
  };
})()
"""


async def main() -> int:
    targets = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
    page = next(t for t in targets if t.get("type") == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=4_000_000) as ws:
        await ws.send(
            json.dumps(
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": PANEL_JS,
                        "awaitPromise": True,
                        "returnByValue": True,
                        "userFacing": True,
                    },
                }
            )
        )
        while True:
            raw = json.loads(await ws.recv())
            if raw.get("id") == 1:
                print(json.dumps(raw.get("result"), ensure_ascii=False)[:2000])
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
