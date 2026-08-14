#!/usr/bin/env python3
"""Debug: abre Globo no IPTVnator, inspeciona erro e forca botao de logs."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

try:
    import websockets
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "websockets"])
    import websockets

FORCE_UI_JS = r"""
(() => {
  // painel flutuante SEMPRE visivel (nao depende do DOM do diagnostic)
  let panel = document.getElementById('iptv-debug-panel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'iptv-debug-panel';
    panel.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:2147483647;width:280px;background:#111;color:#fff;border:2px solid #ffc107;border-radius:10px;padding:10px;font:12px/1.35 Segoe UI,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.45)';
    panel.innerHTML = `
      <div style="font-weight:700;margin-bottom:6px;color:#ffc107">IPTV Debug</div>
      <div id="iptv-debug-status" style="margin-bottom:8px;opacity:.9">aguardando...</div>
      <button id="iptv-copy-error-logs-btn" style="width:100%;padding:10px;margin-bottom:6px;border:0;border-radius:8px;background:#ffc107;color:#111;font-weight:700;cursor:pointer">Copy error logs</button>
      <button id="iptv-open-mpv-btn" style="width:100%;padding:8px;margin-bottom:6px;border:0;border-radius:8px;background:#333;color:#fff;cursor:pointer">Open current in MPV</button>
      <button id="iptv-open-vlc-btn" style="width:100%;padding:8px;border:0;border-radius:8px;background:#333;color:#fff;cursor:pointer">Open current in VLC</button>
    `;
    document.documentElement.appendChild(panel);
  }

  window.__iptvErrorLogBuffer = window.__iptvErrorLogBuffer || [];
  if (!window.__iptvConsoleHooked) {
    window.__iptvConsoleHooked = true;
    ['error','warn','info','log'].forEach((level) => {
      const orig = console[level].bind(console);
      console[level] = (...args) => {
        try {
          const msg = args.map(a => a instanceof Error ? (a.stack||a.message) : (typeof a==='object'?JSON.stringify(a):String(a))).join(' ');
          window.__iptvErrorLogBuffer.push({ts:new Date().toISOString(), level, message: msg});
          if (window.__iptvErrorLogBuffer.length>400) window.__iptvErrorLogBuffer.shift();
        } catch(e){}
        orig(...args);
      };
    });
    window.addEventListener('error', (ev) => {
      window.__iptvErrorLogBuffer.push({ts:new Date().toISOString(), level:'window.onerror', message: `${ev.message} ${ev.filename}:${ev.lineno}\n${ev.error&&ev.error.stack||''}`});
    });
    window.addEventListener('unhandledrejection', (ev) => {
      const r = ev.reason;
      window.__iptvErrorLogBuffer.push({ts:new Date().toISOString(), level:'unhandledrejection', message: r instanceof Error ? (r.stack||r.message) : String(r)});
    });
  }

  function collectUrls() {
    const out = [];
    document.querySelectorAll('video, video source').forEach(el => {
      if (el.src) out.push(el.src);
      if (el.currentSrc) out.push(el.currentSrc);
    });
    const t = document.body.innerText || '';
    const m = t.match(/https?:\/\/[^\s<>"']+/g) || [];
    m.filter(u => /\.m3u8?|\/index\.m3u8|\/live\//i.test(u)).forEach(u => out.push(u));
    return [...new Set(out)];
  }

  function buildReport() {
    const logs = (window.__iptvErrorLogBuffer||[]).slice(-150);
    return [
      '=== IPTVnator error report ===',
      'timestamp: ' + new Date().toISOString(),
      'href: ' + location.href,
      'title: ' + document.title,
      '',
      '=== page text (erro) ===',
      (document.body.innerText||'').slice(0,6000),
      '',
      '=== stream urls ===',
      ...(collectUrls().length?collectUrls():['(none)']),
      '',
      '=== console/traceback ===',
      ...(logs.length? logs.map(l => `[${l.ts}] ${l.level}: ${l.message}`) : ['(vazio)']),
      '',
      '=== end ==='
    ].join('\n');
  }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; }
    catch(e) {
      const ta=document.createElement('textarea'); ta.value=text; document.body.appendChild(ta); ta.select();
      const ok=document.execCommand('copy'); ta.remove(); return ok;
    }
  }

  const copyBtn = document.getElementById('iptv-copy-error-logs-btn');
  copyBtn.onclick = async () => {
    const ok = await copyText(buildReport());
    copyBtn.textContent = ok ? 'COPIADO!' : 'FALHOU';
    setTimeout(()=> copyBtn.textContent='Copy error logs', 1500);
  };

  function clickByText(re) {
    const b=[...document.querySelectorAll('button,a,[role=button]')].find(el => re.test((el.innerText||'').replace(/\s+/g,' ')));
    if (b) { b.click(); return b.innerText.trim().slice(0,60); }
    return null;
  }
  document.getElementById('iptv-open-mpv-btn').onclick = () => clickByText(/Open in MPV/i);
  document.getElementById('iptv-open-vlc-btn').onclick = () => clickByText(/Open in VLC/i);

  const st = document.getElementById('iptv-debug-status');
  const err = /UNSUPPORTED|could not be loaded|Open it in a native player/i.test(document.body.innerText||'');
  st.textContent = err ? 'ERRO de playback detectado' : 'sem painel de erro agora';
  st.style.color = err ? '#ff8a80' : '#a5d6a7';

  return {
    panel: !!document.getElementById('iptv-debug-panel'),
    err,
    href: location.href,
    textSnippet: (document.body.innerText||'').slice(0,500),
    urls: collectUrls(),
    fallbackVersion: window.__iptvAutoFallbackVersion || null,
  };
})()
"""

SEARCH_GLOBO_JS = r"""
(async () => {
  // tenta ir para playlist Brasil
  const side = [...document.querySelectorAll('a,button,div,span')].find(el => /03 Brasil|Brasil/i.test((el.textContent||'').trim()) && (el.textContent||'').length < 40);
  if (side) { side.click(); await new Promise(r=>setTimeout(r,800)); }

  // campo de busca
  let input = document.querySelector('input[type=search], input[placeholder*="Filter"], input[placeholder*="Search"], input[placeholder*="Filter this"]');
  if (!input) {
    // clica lupa/search
    const searchIcon=[...document.querySelectorAll('mat-icon,.mat-icon')].find(i=>/search/i.test(i.textContent||''));
    (searchIcon?.closest('button,a')||searchIcon)?.click();
    await new Promise(r=>setTimeout(r,400));
    input = document.querySelector('input[type=search], input[placeholder*="Filter"], input[placeholder*="Search"], input');
  }
  if (!input) return {err:'no search input', text:(document.body.innerText||'').slice(0,400)};

  input.focus();
  input.value = '';
  input.dispatchEvent(new Event('input', {bubbles:true}));
  await new Promise(r=>setTimeout(r,100));
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  nativeSetter.call(input, 'Globo');
  input.dispatchEvent(new Event('input', {bubbles:true}));
  input.dispatchEvent(new Event('change', {bubbles:true}));
  input.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true, key:'o'}));
  await new Promise(r=>setTimeout(r,900));

  const items = [...document.querySelectorAll('button,a,div,li,mat-list-item,.channel-item')]
    .filter(el => /Globo/i.test(el.textContent||'') && (el.textContent||'').length < 120);
  const names = items.slice(0,15).map(el => (el.textContent||'').replace(/\s+/g,' ').trim());
  // prefer Rede Globo / TV Globo
  const prefer = items.find(el => /Rede Globo|TV Globo Sao Paulo|TV Globo Rio|GloboNews/i.test(el.textContent||'')) || items[0];
  if (prefer) prefer.click();
  await new Promise(r=>setTimeout(r,2500));
  return {
    found: names,
    clicked: prefer && (prefer.textContent||'').replace(/\s+/g,' ').trim().slice(0,80),
    href: location.href,
    body: (document.body.innerText||'').slice(0,800),
  };
})()
"""


async def eval_js(ws, expr, msg_id):
    await ws.send(json.dumps({
        "id": msg_id,
        "method": "Runtime.evaluate",
        "params": {"expression": expr, "awaitPromise": True, "returnByValue": True, "userFacing": True},
    }))
    while True:
        raw = json.loads(await ws.recv())
        if raw.get("id") == msg_id:
            return raw


def get_page():
    targets = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
    return next(t for t in targets if t.get("type") == "page")


async def main():
    page = get_page()
    print("PAGE", page.get("url", "")[:100])
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=8_000_000) as ws:
        r1 = await eval_js(ws, FORCE_UI_JS, 1)
        print("UI", json.dumps(((r1.get("result") or {}).get("result") or {}).get("value"), ensure_ascii=False)[:1500])
        r2 = await eval_js(ws, SEARCH_GLOBO_JS, 2)
        print("GLOBO", json.dumps(((r2.get("result") or {}).get("result") or {}).get("value"), ensure_ascii=False)[:2500])
        await asyncio.sleep(2)
        r3 = await eval_js(ws, FORCE_UI_JS, 3)
        print("UI2", json.dumps(((r3.get("result") or {}).get("result") or {}).get("value"), ensure_ascii=False)[:2000])
        # screenshot via CDP
        await ws.send(json.dumps({"id": 4, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
        while True:
            raw = json.loads(await ws.recv())
            if raw.get("id") == 4:
                import base64
                out = Path.home() / "Documents" / "iptv-org-test" / "debug_globo.png"
                out.write_bytes(base64.b64decode(raw["result"]["data"]))
                print("SHOT", out)
                break


if __name__ == "__main__":
    asyncio.run(main())
