import json, urllib.request, asyncio, websockets
targets = json.load(urllib.request.urlopen("http://127.0.0.1:9222/json/list"))
page = next(t for t in targets if t.get("type") == "page")

async def main():
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=4_000_000) as ws:
        expr = """(async () => {
          const icon=[...document.querySelectorAll('mat-icon')].find(i=>i.textContent.trim()==='settings');
          (icon?.closest('a,button')||icon?.parentElement)?.click();
          await new Promise(r=>setTimeout(r,900));
          const t=document.body.innerText;
          const m=t.match(/Select an option\\n(Embedded MPV[^\\n]*|MPV|VLC|Video\\.js|HTML5[^\\n]*|ArtPlayer[^\\n]*)/);
          const emb=await window.electron.getEmbeddedMpvSupport?.();
          return {playerGuess: m && m[1], hasEmbeddedText: /Embedded MPV \\(Experimental\\)/.test(t), emb};
        })()"""
        await ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": expr, "awaitPromise": True, "returnByValue": True},
        }))
        while True:
            raw = json.loads(await ws.recv())
            if raw.get("id") == 1:
                print(json.dumps(raw, ensure_ascii=False)[:2000])
                break

asyncio.run(main())
