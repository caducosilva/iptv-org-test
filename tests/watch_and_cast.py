#!/usr/bin/env python3
"""Espera a TV sair do standby e dispara o espelhamento automaticamente.

Uso: python tests/watch_and_cast.py [minutos]
Serve para testar o cast sem ficar apertando o botao: assim que a porta 8009
da TV abrir, manda o canal e acompanha as fases ate o resultado final.
"""

from __future__ import annotations

import json
import socket
import sys
import time
import urllib.request
from datetime import datetime

API = "http://127.0.0.1:8769"
TV_HOST = "192.168.0.27"
TV_PORT = 8009
CANAL = {
    "url": "http://45.190.28.50/GLOBO_HD/index.m3u8",
    "title": "TV Globo Rio de Janeiro (720p)",
    "channelName": "TV Globo Rio de Janeiro (720p)",
    "deviceName": TV_HOST,
    "host": TV_HOST,
    "deviceLabel": "50PUG7907/78 @ " + TV_HOST,
}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def tv_acordada() -> bool:
    try:
        with socket.create_connection((TV_HOST, TV_PORT), timeout=2.0):
            return True
    except Exception:  # noqa: BLE001
        return False


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(API + path, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    minutos = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    limite = time.time() + minutos * 60
    log(f"aguardando a TV {TV_HOST}:{TV_PORT} acordar (ate {minutos:.0f} min)...")

    while time.time() < limite:
        if tv_acordada():
            log("TV ACORDOU! porta 8009 aberta")
            break
        time.sleep(3)
    else:
        log("RESULTADO: TIMEOUT - a TV nao acordou no tempo esperado")
        return 2

    # atualiza a lista de dispositivos antes de mandar
    try:
        scan = get("/scan")
        tvs = [d for d in scan.get("devices", []) if d.get("castable")]
        log(f"scan: {len(tvs)} TV(s) utilizavel(is) -> {[d.get('friendlyName') for d in tvs]}")
    except Exception as exc:  # noqa: BLE001
        log(f"WARN scan falhou: {exc}")

    log(f"enviando '{CANAL['title']}' para a TV...")
    try:
        resp = post("/cast", CANAL)
        log(f"comando aceito: started={resp.get('started')} device={resp.get('device')}")
    except Exception as exc:  # noqa: BLE001
        log(f"RESULTADO: ERRO ao chamar /cast: {exc}")
        return 1

    ultima = ""
    fim = time.time() + 170
    while time.time() < fim:
        time.sleep(2)
        try:
            st = get("/cast_status")
        except Exception:  # noqa: BLE001
            continue
        marca = f"{st.get('phase')}|{st.get('message')}"
        if marca != ultima:
            ultima = marca
            log(f"  fase={st.get('phase'):11} player={st.get('player') or '-':10} {str(st.get('message'))[:70]}")
        if not st.get("pending"):
            if st.get("ok"):
                log("RESULTADO: SUCESSO - a TV deve estar espelhando agora")
                log(f"  device={st.get('device')} player={st.get('player')} content={st.get('content_id')}")
                return 0
            log(f"RESULTADO: FALHOU - {st.get('error')}")
            return 1

    log("RESULTADO: TIMEOUT aguardando o resultado do cast")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
