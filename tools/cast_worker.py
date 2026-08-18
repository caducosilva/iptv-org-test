#!/usr/bin/env python3
"""Cast HLS para TV Philips/Chromecast (processo isolado).

Diferenças em relação a versão antiga:
  * publica PROGRESSO em tempo real no result_path (fases: preflight,
    connecting, connected, launching, loading, buffering, success/error),
    para o front mostrar em que etapa o espelhamento está;
  * checa se a TV responde na porta 8009 ANTES de tentar conectar, o que
    evita ficar 12s parado quando a TV está desligada/standby;
  * fallback DLNA (AVTransport) quando a TV não fala Chromecast;
  * NUNCA deixa o status preso em "pending": grava resultado final mesmo
    quando estoura exceção.

Corrige tela preta falsa: a Philips costuma ficar no app "TV aberta" e o
media_controller reporta PLAYING sem content_id. Aqui forçamos o
Default Media Receiver, resolvemos playlist HLS absoluta e validamos status.
"""

from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

UA = "VLC/3.0.20 LibVLC/3.0.20"
DMR_APP_ID = "CC1AD845"  # Default Media Receiver
CAST_PORT = 8009

# ---------------------------------------------------------------- progresso

_RESULT_PATH: Path | None = None
_BASE: dict = {}
_FINAL_WRITTEN = False


def set_result_path(path: Path | None, base: dict) -> None:
    global _RESULT_PATH, _BASE
    _RESULT_PATH = path
    _BASE = dict(base)


def publish(phase: str, message: str, **extra) -> None:
    """Grava progresso parcial (pending=True) no arquivo de status."""
    if _RESULT_PATH is None or _FINAL_WRITTEN:
        return
    data = dict(_BASE)
    data.update(
        {
            "pending": True,
            "ok": None,
            "phase": phase,
            "message": message,
            "progress_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
    )
    data.update({k: v for k, v in extra.items() if v is not None})
    _atomic_write(data)
    print(f"PROGRESS {phase}: {message}", file=sys.stderr, flush=True)


def _atomic_write(data: dict) -> None:
    if _RESULT_PATH is None:
        return
    try:
        tmp = _RESULT_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_RESULT_PATH)
    except Exception:  # noqa: BLE001
        try:
            _RESULT_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


def finish(data: dict) -> int:
    """Grava resultado FINAL (pending=False) e imprime no stdout."""
    global _FINAL_WRITTEN
    out = dict(_BASE)
    out.update(data)
    out["pending"] = False
    out.setdefault("phase", "success" if out.get("ok") else "error")
    out["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _atomic_write(out)
    _FINAL_WRITTEN = True
    print(json.dumps(out, ensure_ascii=False), flush=True)
    return 0 if out.get("ok") else 1


# ------------------------------------------------------------------- rede


def tcp_open(host: str, port: int, timeout: float = 2.5) -> bool:
    """True se a porta aceita conexão (TV ligada e com Cast ativo)."""
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:  # noqa: BLE001
        return False


def http_get(url: str, timeout: float = 12.0) -> tuple[int, str, bytes, str]:
    """Devolve status, tipo, corpo e o endereco em que a resposta parou.

    O endereco final importa: o Chromecast NAO segue redirect. Canal de
    provedor Xtream responde 302 para outro servidor com token na URL, e
    mandar o endereco de antes deixa a TV carregando para sempre, sem erro.
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "*/*",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(512_000)
        ctype = (resp.headers.get("Content-Type") or "").lower()
        return resp.status, ctype, raw, resp.geturl()


def preflight(url: str) -> dict:
    try:
        status, ctype, raw, _final = http_get(url)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"URL inacessivel: {exc}", "url": url}
    if status >= 400:
        return {"ok": False, "error": f"HTTP {status}", "url": url}
    text = raw.decode("utf-8", "replace")
    looks_m3u = "#EXTM3U" in text or "mpegurl" in ctype or url.lower().endswith(".m3u8")
    if not looks_m3u and len(raw) < 64:
        return {"ok": False, "error": "resposta vazia/nao e stream", "url": url, "ctype": ctype}
    return {"ok": True, "ctype": ctype, "bytes": len(raw), "url": url}


def resolve_hls(url: str) -> str:
    """Deixa a URL do jeito que o Chromecast consegue abrir.

    Duas coisas o travam, as duas em silencio (TV parada em "carregando", sem
    erro nenhum de volta): redirect, que ele nao segue, e master playlist de
    canal ao vivo. Aqui o redirect ja vem seguido pelo http_get e o que sai e
    o endereco final; se o que chegou foi uma master, sai a variante de maior
    banda. Pegar a primeira linha solta funcionava por acaso.
    """
    try:
        _status, _ctype, raw, final = http_get(url)
    except Exception:
        return url
    text = raw.decode("utf-8", "replace")
    if "#EXTM3U" not in text:
        return url
    if "#EXTINF" in text:
        return final  # ja e a playlist de midia, no endereco que vale

    lines = text.splitlines()
    best_uri = ""
    best_bw = -1
    pending_bw: int | None = None
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.upper().startswith("#EXT-X-STREAM-INF"):
            pending_bw = 0
            for part in s.split(":", 1)[-1].split(","):
                key, _, value = part.partition("=")
                if key.strip().upper() in ("BANDWIDTH", "AVERAGE-BANDWIDTH"):
                    try:
                        pending_bw = max(pending_bw or 0, int(value.strip().strip('"')))
                    except ValueError:
                        pass
            continue
        if s.startswith("#"):
            continue
        bw = pending_bw if pending_bw is not None else 0
        if bw > best_bw:
            best_bw = bw
            best_uri = s
        pending_bw = None

    return urljoin(final, best_uri) if best_uri else final


# ------------------------------------------------------------- chromecast


def pick_cast(casts, needle: str):
    needle = (needle or "").lower().strip()
    found = [{"name": cc.name, "host": cc.cast_info.host} for cc in casts]
    cast = None
    for cc in casts:
        name = (cc.name or "").lower()
        host = (cc.cast_info.host or "").lower()
        if not needle:
            continue
        if needle == host or needle == name:
            return cc, found
        if needle in name or needle in host:
            if cast is None:
                cast = cc
    if cast is None and casts:
        cast = next(
            (c for c in casts if "pug" in (c.name or "").lower() or "philips" in (c.name or "").lower()),
            casts[0],
        )
    return cast, found


def read_media_state(cast) -> dict:
    mc = cast.media_controller
    try:
        mc.update_status()
    except Exception:
        pass
    st = mc.status
    app_name = ""
    app_id = getattr(cast, "app_id", None)
    if cast.status:
        app_name = cast.status.display_name or ""
        app_id = app_id or getattr(cast.status, "app_id", None)
    return {
        "player": str(getattr(st, "player_state", "") or ""),
        "content": str(getattr(st, "content_id", "") or ""),
        "idle": getattr(st, "idle_reason", None),
        "app_name": app_name or "",
        "app_id": app_id,
    }


def wait_playing(cast, play_url: str, title: str, seconds: int = 28) -> dict:
    """Espera PLAYING/BUFFERING com content_id; reenvia play se IDLE."""
    from pychromecast.controllers.media import STREAM_TYPE_LIVE

    mc = cast.media_controller
    last: dict = {}
    retried = False
    announced_buffer = False
    for i in range(seconds):
        time.sleep(1)
        last = read_media_state(cast)
        player = last["player"]
        content = last["content"]
        idle = last["idle"]
        app_id = last["app_id"]
        app_name = last["app_name"]
        if idle in ("ERROR", "CANCELLED"):
            last["ok"] = False
            last["error"] = f"idle_reason={idle}"
            return last
        good_app = (
            app_id == DMR_APP_ID
            or "receiver" in (app_name or "").lower()
            or "media" in (app_name or "").lower()
            or bool(content)
        )
        if content and player in ("PLAYING", "BUFFERING") and good_app:
            if player == "PLAYING":
                last["ok"] = True
                return last
            if not announced_buffer:
                announced_buffer = True
                publish("buffering", "TV recebeu o canal, carregando o video (buffer)...", player=player)
            continue
        # IDLE com content ou sem: tenta reenviar play uma vez
        if (not content or player in ("IDLE", "UNKNOWN", "")) and i in (6, 12) and not retried:
            retried = True
            publish("loading", "TV nao abriu o player, reenviando o canal...", player=player)
            try:
                if getattr(cast, "app_id", None) != DMR_APP_ID:
                    cast.start_app(DMR_APP_ID)
                    time.sleep(2)
                mc.play_media(
                    play_url,
                    "application/vnd.apple.mpegurl",
                    title=title,
                    autoplay=True,
                    stream_type=STREAM_TYPE_LIVE,
                )
            except Exception:
                pass
    last["ok"] = bool(last.get("content") and last.get("player") == "PLAYING")
    if not last.get("ok"):
        last["error"] = (
            f"nao estabilizou PLAYING (player={last.get('player')} "
            f"content={'sim' if last.get('content') else 'nao'} "
            f"app={last.get('app_name') or last.get('app_id')})"
        )
    return last


def connect_cast(needle: str, host_hint: str = ""):
    import pychromecast
    from pychromecast.discovery import stop_discovery

    browser = None
    cast = None
    found: list[dict] = []

    def is_ip(value: str) -> bool:
        parts = (value or "").split(".")
        return len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)

    # 1) conexao direta por IP (mais estavel na Philips)
    direct = host_hint if is_ip(host_hint) else (needle if is_ip(needle) else "")
    if direct:
        publish("connecting", f"Conectando direto na TV {direct}:{CAST_PORT}...", host=direct)
        try:
            cast = pychromecast.get_chromecast_from_host((direct, CAST_PORT, None, None, None))
            cast.wait(timeout=12)
            found = [{"name": cast.name, "host": direct, "via": "host"}]
            return cast, browser, found
        except Exception as exc:  # noqa: BLE001
            publish("connecting", f"Conexao direta falhou ({exc}); procurando a TV na rede...")
            cast = None

    publish("connecting", "Procurando dispositivos Cast na rede (ate 12s)...")
    casts, browser = pychromecast.get_chromecasts(timeout=12)
    cast, found = pick_cast(casts, needle)
    if cast is None:
        try:
            stop_discovery(browser)
        except Exception:
            pass
        return None, None, found
    publish("connecting", f"TV encontrada: {cast.name}; abrindo canal de controle...")
    cast.wait(timeout=12)
    return cast, browser, found


def ensure_dmr(cast, force: bool = False) -> str | None:
    """Deixa a TV no Default Media Receiver.

    Antes isso fazia SEMPRE quit_app()+start_app(), o que na Philips estourava
    'start app timed out' e deixava a sessao de midia sem vinculo. Agora so
    intervimos quando a TV esta mesmo em outro app.
    """
    err = None
    try:
        if not force and getattr(cast, "app_id", None) == DMR_APP_ID:
            return None  # ja esta no receptor certo
    except Exception:
        pass
    try:
        if force:
            cast.quit_app()
            time.sleep(1.8)
            cast.wait(timeout=8)
    except Exception as exc:  # noqa: BLE001
        err = f"quit_app: {exc}"
    try:
        cast.start_app(DMR_APP_ID)
        time.sleep(2.0)
    except Exception as exc:  # noqa: BLE001
        # nao e fatal: play_media() tambem sobe o receptor sozinho
        err = (err + " | " if err else "") + f"start_app: {exc}"
    return err


def send_media(cast, play_url: str, title: str) -> str | None:
    """Envia a midia e ESPERA a sessao ficar ativa.

    Sem block_until_active o media_controller fica sem sessao e o status volta
    player=UNKNOWN / content_id vazio - era exatamente a falha observada.
    """
    from pychromecast.controllers.media import STREAM_TYPE_LIVE

    mc = cast.media_controller
    mc.play_media(
        play_url,
        "application/x-mpegURL",
        title=title,
        autoplay=True,
        stream_type=STREAM_TYPE_LIVE,
    )
    try:
        mc.block_until_active(timeout=20)
        return None
    except Exception as exc:  # noqa: BLE001
        return f"block_until_active: {exc}"


# -------------------------------------------------------------- DLNA/UPnP


def xml_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def soap_call(control_url: str, service: str, action: str, body_inner: str, timeout: float = 10.0) -> str:
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        f'<s:Body><u:{action} xmlns:u="{service}">{body_inner}</u:{action}></s:Body></s:Envelope>'
    )
    req = urllib.request.Request(
        control_url,
        data=envelope.encode("utf-8"),
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": f'"{service}#{action}"',
            "User-Agent": "IPTV-DLNA/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def didl_meta(url: str, title: str) -> str:
    didl = (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        '<item id="0" parentID="-1" restricted="1">'
        f"<dc:title>{xml_escape(title)}</dc:title>"
        "<upnp:class>object.item.videoItem</upnp:class>"
        '<res protocolInfo="http-get:*:application/x-mpegURL:*">'
        f"{xml_escape(url)}</res></item></DIDL-Lite>"
    )
    return xml_escape(didl)


def cast_via_dlna(avt_control: str, url: str, title: str, device_label: str) -> dict:
    """Envia o stream por AVTransport (TVs sem Chromecast)."""
    service = "urn:schemas-upnp-org:service:AVTransport:1"
    publish("launching", f"Enviando por DLNA para {device_label}...")
    soap_call(
        avt_control,
        service,
        "SetAVTransportURI",
        f"<InstanceID>0</InstanceID><CurrentURI>{xml_escape(url)}</CurrentURI>"
        f"<CurrentURIMetaData>{didl_meta(url, title)}</CurrentURIMetaData>",
    )
    publish("loading", "Canal aceito pela TV; mandando PLAY...")
    soap_call(avt_control, service, "Play", "<InstanceID>0</InstanceID><Speed>1</Speed>")
    return {
        "ok": True,
        "phase": "success",
        "message": f"SUCCESS via DLNA device={device_label}",
        "device": device_label,
        "url": url,
        "source_url": url,
        "title": title,
        "player": "PLAYING",
        "type": "dlna",
    }


# ---------------------------------------------------------------- main


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "usage: cast_worker.py <payload.json>"}))
        return 2
    payload_path = Path(sys.argv[1])
    data = json.loads(payload_path.read_text(encoding="utf-8-sig"))
    url = (data.get("url") or "").strip()
    title = data.get("title") or "IPTV"
    host_hint = (data.get("host") or "").strip()
    needle = (data.get("deviceName") or host_hint or "philips").lower()
    avt_control = (data.get("avt_control") or "").strip()
    device_label = data.get("deviceLabel") or data.get("device") or needle
    result_path = data.get("result_path")

    set_result_path(
        Path(result_path) if result_path else None,
        {
            "url": url,
            "source_url": url,
            "title": title,
            "device": device_label,
            "deviceName": needle,
            "host": host_hint,
        },
    )

    if not url:
        return finish({"ok": False, "error": "url vazia", "message": "ERRO: url vazia"})

    # 1) o canal responde?
    publish("preflight", f"Testando o link do canal '{title}'...")
    pf = preflight(url)
    if not pf.get("ok"):
        return finish(
            {
                "ok": False,
                "error": pf.get("error"),
                "message": f"ERRO no canal (antes da TV): {pf.get('error')}",
            }
        )

    play_url = resolve_hls(url)
    is_chromecast = avt_control in ("", "chromecast") or (data.get("type") or "") == "chromecast"

    # 2) a TV está acessível? (evita 12s parado com a TV desligada)
    if host_hint:
        publish("connecting", f"Verificando se a TV {host_hint} esta ligada...")
        cast_port_open = tcp_open(host_hint, CAST_PORT)
        if not cast_port_open and is_chromecast:
            dlna_port = urlparse(avt_control).port if avt_control.startswith("http") else None
            if not (dlna_port and tcp_open(host_hint, dlna_port)):
                return finish(
                    {
                        "ok": False,
                        "error": f"TV {host_hint} nao responde na porta {CAST_PORT}",
                        "message": (
                            f"TV nao respondeu ({host_hint}:{CAST_PORT} fechada). "
                            "Ligue a TV, confira se esta na mesma rede Wi-Fi e se o "
                            "'Chromecast built-in' esta ativo."
                        ),
                        "hint": "tv_offline",
                    }
                )
        if not cast_port_open and avt_control.startswith("http"):
            is_chromecast = False  # so tem DLNA

    browser = None
    try:
        # 3) caminho DLNA puro
        if not is_chromecast and avt_control.startswith("http"):
            try:
                return finish(cast_via_dlna(avt_control, play_url, title, device_label))
            except Exception as exc:  # noqa: BLE001
                return finish(
                    {
                        "ok": False,
                        "error": str(exc),
                        "message": f"ERRO DLNA: {exc}",
                        "type": "dlna",
                    }
                )

        # 4) caminho Chromecast
        cast, browser, found = connect_cast(needle, host_hint=host_hint)
        if cast is None:
            if avt_control.startswith("http"):
                publish("connecting", "Sem Chromecast; tentando DLNA...")
                try:
                    return finish(cast_via_dlna(avt_control, play_url, title, device_label))
                except Exception as exc:  # noqa: BLE001
                    return finish({"ok": False, "error": str(exc), "message": f"ERRO DLNA: {exc}"})
            return finish(
                {
                    "ok": False,
                    "error": "nenhuma TV Cast na rede",
                    "found": found,
                    "message": "ERRO: nenhuma TV com Cast encontrada na rede",
                    "hint": "tv_offline",
                }
            )

        publish("connected", f"Conectado na TV {cast.name}", device=cast.name)
        publish("launching", "Abrindo o player de midia na TV...")
        dmr_err = ensure_dmr(cast)

        publish("loading", f"Enviando '{title}' para a TV...")
        send_err = send_media(cast, play_url, title)
        if send_err:
            dmr_err = f"{dmr_err} | {send_err}" if dmr_err else send_err

        result = wait_playing(cast, play_url, title, seconds=22)

        # A TV ficou presa em outro app: força o receptor e tenta de novo
        if not result.get("content"):
            publish("launching", "TV nao aceitou de primeira; reiniciando o player da TV...")
            forced_err = ensure_dmr(cast, force=True)
            if forced_err:
                dmr_err = f"{dmr_err} | {forced_err}" if dmr_err else forced_err
            publish("loading", f"Reenviando '{title}' para a TV...")
            send_err2 = send_media(cast, play_url, title)
            if send_err2:
                dmr_err = f"{dmr_err} | {send_err2}" if dmr_err else send_err2
            result = wait_playing(cast, play_url, title, seconds=20)

        player = result.get("player") or ""
        content = result.get("content") or ""
        app_name = result.get("app_name") or ""
        app_id = result.get("app_id")
        common = {
            "device": cast.name,
            "host": cast.cast_info.host,
            "url": play_url,
            "source_url": url,
            "title": title,
            "player": player,
            "app": app_name,
            "app_id": app_id,
            "type": "chromecast",
        }

        if not content:
            err = (
                "TV nao abriu o receptor de midia (ficou em outro app). "
                f"app={app_name or app_id} player={player}"
            )
            if dmr_err:
                err += f" | {dmr_err}"
            return finish({**common, "ok": False, "error": err, "message": f"ERRO: {err}"})

        if not result.get("ok"):
            # BUFFERING prolongado com content_id: TV pegou o stream
            if player == "BUFFERING":
                return finish(
                    {
                        **common,
                        "ok": True,
                        "message": f"SUCCESS player=BUFFERING app={app_name} device={cast.name}",
                        "content_id": content,
                        "note": "aceitou BUFFERING com content_id",
                    }
                )
            err = result.get("error") or f"player={player}"
            return finish(
                {
                    **common,
                    "ok": False,
                    "error": err,
                    "message": f"ERRO: {err}",
                    "content_id": content,
                    "dmr_err": dmr_err,
                }
            )

        return finish(
            {
                **common,
                "ok": True,
                "message": f"SUCCESS player={player} app={app_name} device={cast.name}",
                "content_id": content,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return finish({"ok": False, "error": str(exc), "message": f"ERRO: {exc}"})
    finally:
        if browser is not None:
            try:
                from pychromecast.discovery import stop_discovery

                stop_discovery(browser)
            except Exception:
                pass


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001
        finish({"ok": False, "error": str(exc), "message": f"ERRO fatal: {exc}"})
        raise SystemExit(1)
