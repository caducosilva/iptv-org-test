#!/usr/bin/env python3
"""Scan Chromecast/TV na rede (processo isolado)."""

from __future__ import annotations

import json
import sys


def main() -> int:
    import pychromecast
    from pychromecast.discovery import stop_discovery

    casts, browser = pychromecast.get_chromecasts(timeout=8)
    out = []
    try:
        for cc in casts:
            out.append(
                {
                    "type": "chromecast",
                    "friendlyName": cc.name,
                    "manufacturer": "Google Cast",
                    "modelName": cc.model_name,
                    "host": cc.cast_info.host,
                    "uuid": str(cc.uuid),
                    "avt_control": "chromecast",
                    "location": f"cast://{cc.cast_info.host}",
                }
            )
    finally:
        try:
            stop_discovery(browser)
        except Exception:
            pass
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
