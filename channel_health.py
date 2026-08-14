#!/usr/bin/env python3
"""Cache de saude de canais IPTV (OK / duvida / morto / confirmado).

Regra anti falso-negativo:
- morto so depois de 3 falhas seguidas OU falha dura (DNS/404/recusa)
- canal confirmado por cast OK nao some no filtro esconder mortos
- timeout vira duvida, nao morto imediato
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable

BASE = Path.home() / "Documents" / "iptv-org-test"
HEALTH_PATH = BASE / "channel_health.json"
FAILS_TO_DEAD = 3

# status: unknown | ok | doubt | dead | confirmed
_LOCK = threading.Lock()
_DATA: dict[str, dict] = {}
_LOADED = False
_PROBE_STATE = {
    "running": False,
    "paused": False,
    "done": 0,
    "total": 0,
    "ok": 0,
    "doubt": 0,
    "dead": 0,
    "errors": 0,
    "last_url": "",
    "last_message": "",
    "started_at": "",
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def load_health(force: bool = False) -> None:
    global _LOADED, _DATA
    with _LOCK:
        if _LOADED and not force:
            return
        if HEALTH_PATH.exists():
            try:
                raw = json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("channels"), dict):
                    _DATA = raw["channels"]
                elif isinstance(raw, dict):
                    _DATA = raw
                else:
                    _DATA = {}
            except Exception:
                _DATA = {}
        else:
            _DATA = {}
        _LOADED = True


def save_health() -> None:
    with _LOCK:
        HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": _now(),
            "channels": _DATA,
        }
        tmp = HEALTH_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(HEALTH_PATH)


def get_entry(url: str) -> dict:
    load_health()
    url = (url or "").strip()
    with _LOCK:
        e = _DATA.get(url)
        if not e:
            return {
                "url": url,
                "status": "unknown",
                "fail_count": 0,
                "ok_count": 0,
                "confirmed": False,
                "last_check": "",
                "last_error": "",
                "class": "",
            }
        out = dict(e)
        out["url"] = url
        return out


def stats() -> dict:
    load_health()
    with _LOCK:
        counts = {"unknown": 0, "ok": 0, "doubt": 0, "dead": 0, "confirmed": 0}
        for e in _DATA.values():
            st = e.get("status") or "unknown"
            counts[st] = counts.get(st, 0) + 1
        probe = dict(_PROBE_STATE)
        total = len(_DATA)
    return {"total_tracked": total, "counts": counts, "probe": probe, "path": str(HEALTH_PATH)}


def probe_state() -> dict:
    with _LOCK:
        return dict(_PROBE_STATE)


def set_probe_paused(paused: bool) -> None:
    with _LOCK:
        _PROBE_STATE["paused"] = bool(paused)


def _set_probe(**kwargs) -> None:
    with _LOCK:
        _PROBE_STATE.update(kwargs)


def apply_probe_result(
    url: str,
    ok: bool,
    error: str = "",
    fail_class: str = "",
    name: str = "",
    latency_ms: float | None = None,
    bytes_n: int | None = None,
) -> dict:
    """Atualiza status a partir de um probe. Retorna entry."""
    load_health()
    url = (url or "").strip()
    if not url:
        return {}
    with _LOCK:
        e = dict(_DATA.get(url) or {})
        e.setdefault("fail_count", 0)
        e.setdefault("ok_count", 0)
        e.setdefault("confirmed", bool(e.get("status") == "confirmed"))
        e["name"] = name or e.get("name") or ""
        e["last_check"] = _now()
        e["last_error"] = (error or "")[:240]
        e["class"] = fail_class or ("ok" if ok else "soft")
        if latency_ms is not None:
            try:
                e["latency_ms"] = round(float(latency_ms), 1)
            except Exception:
                pass
        if bytes_n is not None:
            try:
                e["bytes"] = int(bytes_n)
            except Exception:
                pass
        if ok:
            e["ok_count"] = int(e.get("ok_count") or 0) + 1
            e["fail_count"] = 0
            if e.get("confirmed"):
                e["status"] = "confirmed"
            else:
                e["status"] = "ok"
        else:
            e["fail_count"] = int(e.get("fail_count") or 0) + 1
            hard = fail_class == "hard"
            if e.get("confirmed"):
                # confirmado: so vira duvida; nunca morto automatico
                e["status"] = "doubt" if e["fail_count"] >= 1 else "confirmed"
            elif hard or e["fail_count"] >= FAILS_TO_DEAD:
                e["status"] = "dead"
            else:
                e["status"] = "doubt"
        e["signal"] = signal_score(e)
        _DATA[url] = e
        out = dict(e)
        out["url"] = url
    return out


def signal_score(entry: dict) -> int:
    """Qualidade 0-100 para ordenar lista (melhor = maior)."""
    st = (entry.get("status") or "unknown").lower()
    fails = int(entry.get("fail_count") or 0)
    lat = entry.get("latency_ms")
    if st == "dead":
        return 0
    if st == "doubt":
        return max(5, 32 - fails * 6)
    if st == "unknown":
        return 38
    base = 94 if st == "confirmed" else 76
    if lat is not None:
        try:
            ms = float(lat)
            if ms < 350:
                base += 6
            elif ms < 800:
                base += 3
            elif ms < 1500:
                base += 0
            elif ms < 3000:
                base -= 8
            else:
                base -= 18
        except Exception:
            pass
    ok_n = int(entry.get("ok_count") or 0)
    if ok_n >= 3:
        base += 2
    if st == "confirmed":
        base = max(base, 88)
    return max(0, min(100, int(base)))


def mark_confirmed(url: str, name: str = "") -> dict:
    load_health()
    url = (url or "").strip()
    if not url:
        return {}
    with _LOCK:
        e = dict(_DATA.get(url) or {})
        e["status"] = "confirmed"
        e["confirmed"] = True
        e["fail_count"] = 0
        e["ok_count"] = int(e.get("ok_count") or 0) + 1
        e["last_check"] = _now()
        e["last_error"] = ""
        e["class"] = "cast_ok"
        e["signal"] = signal_score(e)
        if name:
            e["name"] = name
        _DATA[url] = e
        out = dict(e)
        out["url"] = url
    save_health()
    return out


def mark_cast_fail(url: str, error: str = "", name: str = "") -> dict:
    """Falha de cast: duvida, nao mata canal confirmado."""
    return apply_probe_result(
        url,
        ok=False,
        error=error or "cast falhou",
        fail_class="soft",
        name=name,
    )


def enrich_channel(ch: dict) -> dict:
    url = (ch.get("url") or "").strip()
    e = get_entry(url)
    out = dict(ch)
    out["health"] = e.get("status") or "unknown"
    out["health_fail"] = e.get("fail_count") or 0
    out["health_error"] = e.get("last_error") or ""
    out["confirmed"] = bool(e.get("confirmed") or e.get("status") == "confirmed")
    sig = e.get("signal")
    if sig is None:
        sig = signal_score(e)
    out["signalStrength"] = int(sig)
    out["latency_ms"] = e.get("latency_ms")
    return out


def should_hide(entry_or_ch: dict, hide_dead: bool) -> bool:
    if not hide_dead:
        return False
    st = entry_or_ch.get("health") or entry_or_ch.get("status") or "unknown"
    confirmed = bool(entry_or_ch.get("confirmed") or st == "confirmed")
    if confirmed:
        return False
    return st == "dead"


def classify_probe_error(error: str) -> str:
    msg = (error or "").lower()
    hard_tokens = (
        "10061",
        "actively refused",
        "recusou",
        "404",
        "410",
        "getaddrinfo",
        "11001",
        "dns",
        "name or service not known",
        "nodename nor servname",
        "no such host",
        "http 403",
        "http 401",
        "http 451",
    )
    if any(t in msg for t in hard_tokens):
        return "hard"
    return "soft"


def attach_health_to_list(
    channels: list[dict],
    hide_dead: bool = False,
    sort_by_signal: bool = True,
) -> list[dict]:
    out = []
    for ch in channels:
        enriched = enrich_channel(ch)
        if should_hide(enriched, hide_dead):
            continue
        out.append(enriched)
    if sort_by_signal:
        out.sort(
            key=lambda c: (
                -(int(c.get("signalStrength") or 0)),
                (c.get("name") or "").lower(),
            )
        )
    return out


def run_batch_probe(
    items: list[dict],
    probe_fn: Callable[[str], dict],
    workers: int = 8,
    save_every: int = 20,
) -> dict:
    """Probe paralelo. items: {url, name?}."""
    load_health()
    urls = []
    seen = set()
    for it in items:
        u = (it.get("url") or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        urls.append({"url": u, "name": it.get("name") or ""})
    total = len(urls)
    _set_probe(
        running=True,
        paused=False,
        done=0,
        total=total,
        ok=0,
        doubt=0,
        dead=0,
        errors=0,
        last_url="",
        last_message="iniciando",
        started_at=_now(),
    )
    done = ok_n = doubt_n = dead_n = err_n = 0

    def one(item: dict) -> dict:
        url = item["url"]
        name = item.get("name") or ""
        try:
            res = probe_fn(url)
        except Exception as exc:  # noqa: BLE001
            res = {"ok": False, "error": str(exc)}
        ok = bool(res.get("ok"))
        err = res.get("error") or ""
        fail_class = "ok" if ok else classify_probe_error(err)
        entry = apply_probe_result(
            url,
            ok=ok,
            error=err,
            fail_class=fail_class,
            name=name,
            latency_ms=res.get("latency_ms"),
            bytes_n=res.get("bytes"),
        )
        return {"url": url, "ok": ok, "entry": entry, "error": err}

    try:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futs = {pool.submit(one, it): it for it in urls}
            for fut in as_completed(futs):
                with _LOCK:
                    if _PROBE_STATE.get("paused"):
                        pass
                try:
                    r = fut.result()
                except Exception as exc:  # noqa: BLE001
                    err_n += 1
                    _set_probe(errors=err_n, last_message=str(exc)[:160])
                    continue
                done += 1
                st = (r.get("entry") or {}).get("status")
                if r.get("ok"):
                    ok_n += 1
                elif st == "dead":
                    dead_n += 1
                else:
                    doubt_n += 1
                _set_probe(
                    done=done,
                    ok=ok_n,
                    doubt=doubt_n,
                    dead=dead_n,
                    errors=err_n,
                    last_url=r.get("url") or "",
                    last_message=f"{st}: {(r.get('error') or 'ok')[:100]}",
                )
                if done % save_every == 0:
                    save_health()
    finally:
        save_health()
        _set_probe(running=False, last_message="concluido")
    return stats()


def _parse_last_check(ts: str) -> float:
    if not ts:
        return 0.0
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S").timestamp()
    except Exception:
        return 0.0


def background_catalog_probe(
    get_items_fn: Callable[[], list[dict]],
    probe_fn: Callable[[str], dict],
    interval: float = 90.0,
    batch_size: int = 25,
    workers: int = 4,
    stale_minutes: float = 12.0,
) -> None:
    """Loop leve: unknown -> doubt -> stale (recheck), sem saturar a rede."""

    def loop() -> None:
        time.sleep(10)
        while True:
            try:
                if probe_state().get("running"):
                    time.sleep(5)
                    continue
                if probe_state().get("paused"):
                    time.sleep(3)
                    continue
                items = get_items_fn() or []
                load_health()
                now = time.time()
                stale_after = stale_minutes * 60.0
                unknown: list[dict] = []
                doubt: list[dict] = []
                stale: list[dict] = []
                for it in items:
                    url = (it.get("url") or "").strip()
                    if not url:
                        continue
                    e = get_entry(url)
                    st = e.get("status") or "unknown"
                    row = {"url": url, "name": it.get("name") or ""}
                    if st == "unknown":
                        unknown.append(row)
                    elif st == "doubt":
                        doubt.append(row)
                    elif st in ("ok", "confirmed"):
                        age = now - _parse_last_check(e.get("last_check") or "")
                        if age >= stale_after:
                            stale.append(row)
                # prioriza descoberta; recheck lento dos bons
                batch = (unknown[:batch_size] + doubt[: max(0, batch_size // 3)])[:batch_size]
                if len(batch) < batch_size:
                    need = batch_size - len(batch)
                    batch.extend(stale[:need])
                if batch:
                    print(
                        f"INFO: probe background lote={len(batch)} "
                        f"unknown={len(unknown)} doubt={len(doubt)} stale={len(stale)}",
                        flush=True,
                    )
                    run_batch_probe(batch, probe_fn, workers=workers, save_every=8)
                    # se ainda tem muito unknown, espera menos; senao respira
                    wait = interval if unknown else max(interval, 150.0)
                else:
                    wait = max(interval, 180.0)
            except Exception as exc:  # noqa: BLE001
                print("WARN probe background:", exc, flush=True)
                wait = interval
            time.sleep(wait)

    threading.Thread(target=loop, daemon=True, name="channel-health-probe").start()
