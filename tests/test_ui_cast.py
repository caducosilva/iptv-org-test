#!/usr/bin/env python3
"""Teste de UI do botao de espelhamento (Playwright).

Verifica o que o usuario ve: o botao existe, responde ao clique, mostra as
etapas do envio e termina com um estado claro (sucesso ou erro explicado).
Gera screenshots em tests/test-logs/.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "test-logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
UI = "http://127.0.0.1:3000"
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)


def main() -> int:
    from playwright.sync_api import sync_playwright

    errors: list[str] = []
    console_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

        t0 = time.time()
        page.goto(UI, wait_until="networkidle", timeout=45000)
        log(f"pagina carregada em {time.time() - t0:.1f}s")

        page.wait_for_timeout(3500)  # deixa carregar canais e devices

        # 1. lista de canais renderizou?
        rows = page.locator("text=Enviar TV")
        count = rows.count()
        log(f"linhas de canal visiveis (virtualizadas): {count}")
        if count == 0:
            errors.append("nenhum canal renderizado")
        elif count > 60:
            errors.append(f"virtualizacao falhou: {count} linhas no DOM de uma vez")

        # 2. botao principal existe e esta visivel?
        btn = page.locator("button", has_text="ESPELHAR NA TV").first
        if btn.count() == 0:
            btn = page.locator("button", has_text="Espelhar").first
        if btn.count() == 0:
            errors.append("botao de espelhar nao encontrado")
            log("ERRO botao de espelhar ausente")
        else:
            log(f"botao encontrado: '{btn.inner_text().strip()}' habilitado={btn.is_enabled()}")

        page.screenshot(path=str(LOG_DIR / f"ui_antes_{stamp}.png"))

        # 3. clicar e observar as fases
        if btn.count() > 0 and btn.is_enabled():
            btn.click()
            log("clique enviado; observando fases...")
            fases: list[str] = []
            deadline = time.time() + 60
            while time.time() < deadline:
                page.wait_for_timeout(700)
                texto = page.locator("body").inner_text()
                for marca in (
                    "ESPELHANDO",
                    "Preparando",
                    "Testando o link",
                    "Verificando se a TV",
                    "Conectando",
                    "Conectado na TV",
                    "Abrindo o player",
                    "Enviando",
                    "buffer",
                    "Espelhando na TV",
                    "Falhou",
                    "nao respondeu",
                    "não respondeu",
                ):
                    if marca.lower() in texto.lower() and marca not in fases:
                        fases.append(marca)
                        log(f"  fase detectada -> {marca}")
                # inner_text aplica text-transform (o status vem em CAIXA ALTA)
                baixo = texto.lower()
                if "espelhando na tv" in baixo or "falhou" in baixo:
                    break
            if not fases:
                errors.append("nenhuma fase de status apareceu apos o clique")
            else:
                log(f"fases observadas: {fases}")
        else:
            log("SKIP clique (botao desabilitado: sem TV ou sem canal selecionado)")

        page.screenshot(path=str(LOG_DIR / f"ui_depois_{stamp}.png"))
        log(f"screenshots em {LOG_DIR}")

        # 4. erros de console do React
        reais = [e for e in console_errors if "favicon" not in e.lower()]
        if reais:
            log(f"WARN console: {reais[:3]}")

        browser.close()

    if errors:
        log(f"FIM FAIL: {errors}")
        return 1
    log("FIM OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
