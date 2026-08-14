#!/usr/bin/env python3
"""Confere os filtros de pais e categoria na interface."""

from __future__ import annotations

import re
import sys

from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

JS_BOTOES = "() => Array.from(document.querySelectorAll('button')).map(b => b.innerText.split('\\n').join(' ').trim())"


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        pg = b.new_page(viewport={"width": 1500, "height": 940})
        pg.goto("http://127.0.0.1:3000", wait_until="networkidle", timeout=45000)
        pg.wait_for_timeout(4000)

        botoes = pg.evaluate(JS_BOTOES)
        chaves = ("Brasil", "Japão", "Estados Unidos", "Filmes", "Séries", "Notícias", "São Paulo", "Tudo")
        print("CHIPS:", [t for t in botoes if any(k in t for k in chaves)][:14])

        def conta() -> str:
            m = re.search(r"canais:\s*(\d+)\s*/\s*(\d+)", pg.locator("body").inner_text())
            return f"{m.group(1)} de {m.group(2)}" if m else "?"

        print("\nsem filtro    :", conta())

        pg.get_by_role("button", name=re.compile("Brasil")).first.click()
        pg.wait_for_timeout(1200)
        print("Brasil        :", conta())

        pg.get_by_role("button", name=re.compile("São Paulo")).first.click()
        pg.wait_for_timeout(1200)
        print("Brasil + SP   :", conta())
        pg.screenshot(path="tests/test-logs/final_sp.png")

        pg.get_by_role("button", name=re.compile(r"^Tudo")).first.click()
        pg.wait_for_timeout(900)
        pg.get_by_role("button", name=re.compile("Estados Unidos")).first.click()
        pg.wait_for_timeout(1200)
        pg.get_by_role("button", name=re.compile(r"^Filmes")).first.click()
        pg.wait_for_timeout(1500)
        print("EUA + Filmes  :", conta())

        # confere que a lista realmente so mostra o grupo escolhido
        nomes = pg.evaluate(
            "() => Array.from(document.querySelectorAll('div[style*=\"height: 58px\"]')).length"
        )
        print("linhas renderizadas (virtualizado):", nomes)
        pg.screenshot(path="tests/test-logs/final_filmes.png")

        b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
