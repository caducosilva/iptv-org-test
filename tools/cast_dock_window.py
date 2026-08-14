#!/usr/bin/env python3
"""Janela Cast colada na lateral do IPTVnator (fora do app)."""

from __future__ import annotations

import json
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
import ctypes
from ctypes import windll, wintypes
from tkinter import ttk

API = "http://127.0.0.1:8769"
DOCK_W = 380
GLOBO_RJ = {
    "name": "TV Globo Rio de Janeiro (720p)",
    "url": "http://45.190.28.50/GLOBO_HD/index.m3u8",
    "playlist": "atalho",
}

user32 = windll.user32
kernel32 = windll.kernel32

# DPI: evita janela "descolar" em monitores com escala
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
HWND_TOP = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOPMOST = 0x00000008


class RECT(wintypes.RECT):
    pass


def api_get(path: str, timeout: float = 20.0) -> dict:
    with urllib.request.urlopen(API + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_post(path: str, payload: dict, timeout: float = 30.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _process_basename(pid: int) -> str:
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return (buf.value or "").replace("/", "\\").split("\\")[-1].lower()
    finally:
        kernel32.CloseHandle(handle)
    return ""


def find_iptvnator_hwnd() -> int:
    """Acha a janela principal do IPTVnator.exe (maior area visivel)."""
    best_hwnd = 0
    best_area = 0

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _lparam):
        nonlocal best_hwnd, best_area
        if not user32.IsWindowVisible(hwnd):
            return True
        title_buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, title_buf, 512)
        title = (title_buf.value or "").strip()
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        exe = _process_basename(int(pid.value))
        ok = False
        if title.lower() == "iptvnator" or title.lower().startswith("iptvnator"):
            ok = True
        if exe == "iptvnator.exe":
            ok = True
        if not ok:
            return True
        rect = RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        w = int(rect.right) - int(rect.left)
        h = int(rect.bottom) - int(rect.top)
        if w < 160 or h < 160:
            # tenta DWM
            try:
                r2 = RECT()
                if ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r2), ctypes.sizeof(r2)) == 0:
                    w = int(r2.right) - int(r2.left)
                    h = int(r2.bottom) - int(r2.top)
            except Exception:
                pass
        if w < 160 or h < 160:
            return True
        area = w * h
        if area > best_area:
            best_area = area
            best_hwnd = int(hwnd)
        return True

    user32.EnumWindows(enum_proc, 0)
    return best_hwnd


def window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    if not hwnd or not user32.IsWindow(hwnd):
        return None
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    left, top, right, bottom = int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)
    if right - left <= 1 or bottom - top <= 1:
        # fallback DWM bounds
        try:
            dwm = ctypes.windll.dwmapi
            r2 = RECT()
            hr = dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r2), ctypes.sizeof(r2))
            if hr == 0:
                left, top, right, bottom = int(r2.left), int(r2.top), int(r2.right), int(r2.bottom)
        except Exception:
            pass
    if right - left <= 1 or bottom - top <= 1:
        return None
    return left, top, right, bottom


def tk_hwnd(root: tk.Misc) -> int:
    root.update_idletasks()
    hwnd = int(root.winfo_id())
    # sobe ate a janela top-level Win32
    for _ in range(8):
        parent = int(user32.GetParent(hwnd) or 0)
        if not parent or parent == hwnd:
            break
        hwnd = parent
    return hwnd


def move_hwnd(hwnd: int, x: int, y: int, w: int, h: int, after_hwnd: int = 0) -> bool:
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    insert_after = after_hwnd if after_hwnd else HWND_TOP
    ok = bool(
        user32.SetWindowPos(
            hwnd,
            insert_after,
            int(x),
            int(y),
            int(w),
            int(h),
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
    )
    return ok


def clear_topmost(hwnd: int) -> None:
    if not hwnd or not user32.IsWindow(hwnd):
        return
    user32.SetWindowPos(
        hwnd,
        HWND_NOTOPMOST,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
    )


def set_owner(child_hwnd: int, owner_hwnd: int) -> None:
    """Faz o Cast ser 'filho' do IPTVnator no z-order (sobe com ele, nao fica acima de tudo)."""
    if not child_hwnd or not owner_hwnd:
        return
    if not user32.IsWindow(child_hwnd) or not user32.IsWindow(owner_hwnd):
        return
    try:
        user32.SetWindowLongPtrW(child_hwnd, GWLP_HWNDPARENT, owner_hwnd)
    except Exception:
        user32.SetWindowLongW(child_hwnd, GWLP_HWNDPARENT, owner_hwnd)


class CastDockApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Cast Companion")
        self.root.configure(bg="#FFFDE7")
        self.root.geometry(f"{DOCK_W}x700+100+100")
        self.root.minsize(DOCK_W, 420)
        # NAO fica topmost global - sobe so junto com o IPTVnator
        try:
            self.root.attributes("-topmost", False)
        except tk.TclError:
            pass
        try:
            self.root.attributes("-toolwindow", True)
        except tk.TclError:
            pass

        self.pick: dict | None = None
        self.preview_ok = False
        self.cast_busy = False
        self.devices: list[dict] = []
        self._search_after: str | None = None
        self._last_anchor: tuple[int, int, int, int] | None = None
        self._iptv_hwnd = 0
        self._dock_hwnd = 0
        self._owner_set_for = 0
        self._catalog_version = -1
        self._folder_lbl_text = ""

        self._build()
        self.root.update_idletasks()
        self._dock_hwnd = tk_hwnd(self.root)
        clear_topmost(self._dock_hwnd)
        try:
            ex = user32.GetWindowLongW(self._dock_hwnd, GWL_EXSTYLE)
            ex = (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW & ~WS_EX_TOPMOST
            user32.SetWindowLongW(self._dock_hwnd, GWL_EXSTYLE, ex)
        except Exception:
            pass
        self.root.after(30, self._tick_dock)
        self.root.after(400, self._boot_data)

    def _build(self) -> None:
        pad = {"padx": 10, "pady": 4}
        title = tk.Label(
            self.root,
            text="CAST (grudado no IPTVnator)",
            bg="#FFEB3B",
            fg="#111",
            font=("Segoe UI", 12, "bold"),
            relief="solid",
            bd=2,
        )
        title.pack(fill="x", padx=8, pady=8)

        self.folder_lbl = tk.Label(
            self.root,
            text="pasta: (carregando)",
            bg="#FFFDE7",
            fg="#0D47A1",
            font=("Segoe UI", 8, "bold"),
            wraplength=DOCK_W - 24,
            justify="left",
        )
        self.folder_lbl.pack(fill="x", padx=10)

        self.status = tk.Label(
            self.root,
            text="aguardando IPTVnator...",
            bg="#FFFDE7",
            fg="#B71C1C",
            font=("Segoe UI", 9, "bold"),
            wraplength=DOCK_W - 24,
            justify="left",
        )
        self.status.pack(fill="x", **pad)

        tk.Label(self.root, text="Lista M3U", bg="#FFFDE7", fg="#111", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=10
        )
        self.playlist_var = tk.StringVar(value="TODAS")
        self.playlist_combo = ttk.Combobox(
            self.root,
            textvariable=self.playlist_var,
            state="readonly",
            font=("Segoe UI", 10, "bold"),
            values=["TODAS"],
        )
        self.playlist_combo.pack(fill="x", padx=10, pady=4)
        self.playlist_combo.bind("<<ComboboxSelected>>", lambda _e: self._reload_channels())

        tk.Label(self.root, text="Buscar canal (vazio = todos)", bg="#FFFDE7", fg="#111", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=10
        )
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            self.root,
            textvariable=self.search_var,
            font=("Segoe UI", 11, "bold"),
            bg="#fff",
            fg="#111",
            relief="solid",
            bd=2,
        )
        self.search_entry.pack(fill="x", padx=10, pady=4)
        self.search_entry.bind("<KeyRelease>", self._on_search_key)

        filt_row = tk.Frame(self.root, bg="#FFFDE7")
        filt_row.pack(fill="x", padx=10, pady=2)
        self.hide_dead_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            filt_row,
            text="esconder mortos",
            variable=self.hide_dead_var,
            bg="#FFFDE7",
            fg="#111",
            font=("Segoe UI", 9, "bold"),
            activebackground="#FFFDE7",
            command=self._reload_channels,
        ).pack(side="left")
        tk.Button(
            filt_row,
            text="Testar visiveis",
            font=("Segoe UI", 8, "bold"),
            bg="#FFE082",
            fg="#111",
            relief="solid",
            bd=1,
            command=lambda: threading.Thread(target=self._probe_visible, daemon=True).start(),
        ).pack(side="right")

        self.health_lbl = tk.Label(
            self.root,
            text="saude: aguardando",
            bg="#FFFDE7",
            fg="#0D47A1",
            font=("Segoe UI", 8, "bold"),
            anchor="w",
            wraplength=DOCK_W - 24,
            justify="left",
        )
        self.health_lbl.pack(fill="x", padx=10)

        self.count_lbl = tk.Label(
            self.root,
            text="canais: 0",
            bg="#FFFDE7",
            fg="#111",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.count_lbl.pack(fill="x", padx=10)

        list_frame = tk.Frame(self.root, bg="#fff", highlightbackground="#111", highlightthickness=2)
        list_frame.pack(fill="both", expand=True, padx=10, pady=4)
        self.channel_list = tk.Listbox(
            list_frame,
            font=("Segoe UI", 10, "bold"),
            bg="#FFF59D",
            fg="#111",
            selectbackground="#76FF03",
            selectforeground="#111",
            activestyle="none",
            relief="flat",
        )
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.channel_list.yview)
        self.channel_list.configure(yscrollcommand=sb.set)
        self.channel_list.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.channel_list.bind("<<ListboxSelect>>", self._on_select_channel)
        self._channels: list[dict] = []

        self.preview_lbl = tk.Label(
            self.root,
            text="preview: nenhum canal",
            bg="#fff",
            fg="#111",
            font=("Segoe UI", 9, "bold"),
            relief="solid",
            bd=2,
            wraplength=DOCK_W - 24,
            justify="left",
            height=3,
        )
        self.preview_lbl.pack(fill="x", padx=10, pady=4)

        tk.Label(self.root, text="TV destino", bg="#FFFDE7", fg="#111", font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=10
        )
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(
            self.root,
            textvariable=self.device_var,
            state="readonly",
            font=("Segoe UI", 10, "bold"),
        )
        self.device_combo.pack(fill="x", padx=10, pady=4)

        self.log = tk.Text(
            self.root,
            height=6,
            font=("Consolas", 8),
            bg="#fff",
            fg="#111",
            relief="solid",
            bd=2,
        )
        self.log.pack(fill="x", padx=10, pady=4)

        self.cast_btn = tk.Button(
            self.root,
            text="Escolha um canal",
            font=("Segoe UI", 11, "bold"),
            bg="#BDBDBD",
            fg="#111",
            relief="solid",
            bd=3,
            command=self._cast_now,
            state="disabled",
        )
        self.cast_btn.pack(fill="x", padx=10, pady=4)

        row = tk.Frame(self.root, bg="#FFFDE7")
        row.pack(fill="x", padx=10, pady=6)
        tk.Button(
            row,
            text="Re-scan TVs",
            font=("Segoe UI", 9, "bold"),
            bg="#FFAB40",
            fg="#111",
            relief="solid",
            bd=2,
            command=lambda: threading.Thread(target=self._scan_devices, daemon=True).start(),
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))
        tk.Button(
            row,
            text="Globo RJ",
            font=("Segoe UI", 9, "bold"),
            bg="#76FF03",
            fg="#111",
            relief="solid",
            bd=2,
            command=lambda: self._select_channel(GLOBO_RJ),
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _log(self, phase: str, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {phase}: {msg}\n"
        self.log.insert("end", line)
        self.log.see("end")

    def set_status(self, msg: str, color: str = "#B71C1C") -> None:
        self.status.configure(text=msg, fg=color)

    def _update_cast_btn(self) -> None:
        if self.cast_busy:
            self.cast_btn.configure(text="ESPELHANDO... aguarde", state="disabled", bg="#FF9800")
            return
        if not self.pick:
            self.cast_btn.configure(text="Escolha um canal", state="disabled", bg="#BDBDBD")
            return
        if not self.device_var.get():
            self.cast_btn.configure(text="Selecione a TV", state="disabled", bg="#BDBDBD")
            return
        name = (self.pick.get("name") or "canal")[:22]
        if self.preview_ok:
            self.cast_btn.configure(text=f"Espelhar: {name}", state="normal", bg="#76FF03")
        else:
            # permite tentar mesmo com preview falho (anti falso-negativo)
            self.cast_btn.configure(
                text=f"Tentar mesmo assim: {name}",
                state="normal",
                bg="#FFCC80",
            )

    def _boot_data(self) -> None:
        threading.Thread(target=self._scan_devices, daemon=True).start()
        threading.Thread(target=self._load_playlists, daemon=True).start()
        self.search_var.set("")
        self._search_channels("")
        self.root.after(2000, self._poll_catalog)
        self.root.after(3500, self._poll_health)

    def _poll_health(self) -> None:
        def work() -> None:
            try:
                data = api_get("/probe/status", timeout=8)
            except Exception:
                self.root.after(5000, self._poll_health)
                return

            def apply() -> None:
                st = (data.get("stats") or {}).get("counts") or {}
                probe = data.get("probe") or {}
                txt = (
                    f"OK={st.get('ok',0)} duvida={st.get('doubt',0)} "
                    f"morto={st.get('dead',0)} conf={st.get('confirmed',0)} "
                    f"?={st.get('unknown',0)}"
                )
                if probe.get("running"):
                    txt += f" | testando {probe.get('done',0)}/{probe.get('total',0)}"
                self.health_lbl.configure(text=f"saude: {txt}")
                self.root.after(4000, self._poll_health)

            self.root.after(0, apply)

        threading.Thread(target=work, daemon=True).start()

    def _poll_catalog(self) -> None:
        def work() -> None:
            try:
                info = api_get("/catalog", timeout=10)
            except Exception:
                self.root.after(2500, self._poll_catalog)
                return

            def apply() -> None:
                ver = int(info.get("version") or 0)
                folder = info.get("folder") or ""
                if folder and folder != self._folder_lbl_text:
                    self._folder_lbl_text = folder
                    self.folder_lbl.configure(text=f"pasta M3U: {folder}")
                if ver != self._catalog_version:
                    old = self._catalog_version
                    self._catalog_version = ver
                    if old >= 0:
                        self.set_status(
                            f"listas atualizadas v{ver} ({info.get('channels')} canais)",
                            "#1B5E20",
                        )
                        self._log("scan", f"catalogo mudou -> v{ver}")
                        self._load_playlists()
                        self._reload_channels()
                self.root.after(2000, self._poll_catalog)

            self.root.after(0, apply)

        threading.Thread(target=work, daemon=True).start()

    def _load_playlists(self) -> None:
        try:
            data = api_get("/playlists", timeout=30)
            items = data.get("playlists") or []
            folder = data.get("folder") or ""
            ver = int(data.get("version") or 0)
        except Exception:
            items = []
            folder = ""
            ver = self._catalog_version

        def apply() -> None:
            if folder:
                self._folder_lbl_text = folder
                self.folder_lbl.configure(text=f"pasta M3U: {folder}")
            if ver:
                self._catalog_version = ver
            names = ["TODAS"] + [
                f"{it.get('name')} ({it.get('count')})" for it in items
            ]
            self._playlist_raw = ["TODAS"] + [str(it.get("name") or "") for it in items]
            cur = self.playlist_var.get()
            self.playlist_combo["values"] = names
            if cur in names:
                self.playlist_var.set(cur)
            else:
                self.playlist_var.set("TODAS")

        self.root.after(0, apply)

    def _selected_playlist_filter(self) -> str:
        label = self.playlist_var.get() or "TODAS"
        if label == "TODAS" or not hasattr(self, "_playlist_raw"):
            return ""
        names = list(self.playlist_combo["values"])
        try:
            idx = names.index(label)
            raw = self._playlist_raw[idx]
            return "" if raw == "TODAS" else raw
        except Exception:
            return ""

    def _reload_channels(self) -> None:
        self._search_channels(self.search_var.get().strip())

    def _on_search_key(self, _evt=None) -> None:
        if self._search_after:
            self.root.after_cancel(self._search_after)
        q = self.search_var.get().strip()
        self._search_after = self.root.after(280, lambda: self._search_channels(q))

    def _search_channels(self, q: str) -> None:
        playlist = self._selected_playlist_filter()
        hide_dead = bool(self.hide_dead_var.get()) if hasattr(self, "hide_dead_var") else False

        def work() -> None:
            try:
                params = f"limit=25000&q={urllib.parse.quote(q)}"
                if playlist:
                    params += f"&playlist={urllib.parse.quote(playlist)}"
                if hide_dead:
                    params += "&hide_dead=1"
                self.root.after(0, lambda: self.set_status("carregando canais das listas M3U...", "#E65100"))
                data = api_get("/channels?" + params, timeout=120)
                chans = data.get("channels") or []
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self.set_status(f"busca falhou: {exc}"))
                return
            self.root.after(0, lambda: self._fill_channels(chans, q, playlist))

        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _badge(ch: dict) -> str:
        st = (ch.get("health") or "unknown").lower()
        if st == "confirmed":
            return "[OK*]"
        if st == "ok":
            return "[OK]"
        if st == "doubt":
            return "[?]"
        if st == "dead":
            return "[X]"
        return "[ ]"

    def _fill_channels(self, chans: list[dict], q: str = "", playlist: str = "") -> None:
        self._channels = chans
        self.channel_list.delete(0, "end")
        for ch in chans:
            pl = ch.get("playlist") or ""
            badge = self._badge(ch)
            self.channel_list.insert("end", f"{badge} {ch.get('name')}  |  {pl}")
        self.count_lbl.configure(text=f"canais: {len(chans)}")
        if not chans:
            self.set_status("nenhum canal")
        else:
            filt = playlist or "TODAS"
            qtxt = q or "(todos)"
            hide = " | sem mortos" if getattr(self, "hide_dead_var", None) and self.hide_dead_var.get() else ""
            self.set_status(f"{len(chans)} canais | lista={filt} | busca={qtxt}{hide}", "#1B5E20")

    def _probe_visible(self) -> None:
        chans = list(self._channels[:80])
        if not chans:
            self.root.after(0, lambda: self.set_status("nenhum canal visivel para testar"))
            return
        self.root.after(0, lambda: self.set_status(f"testando {len(chans)} canais visiveis...", "#E65100"))
        self._log("probe", f"iniciando teste de {len(chans)} canais")
        try:
            api_post("/probe/batch", {"channels": chans, "workers": 6}, timeout=20)
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: self.set_status(f"probe falhou: {exc}"))
            return
        # espera terminar e atualiza lista
        for _ in range(90):
            time.sleep(1)
            try:
                st = api_get("/probe/status", timeout=8)
                probe = st.get("probe") or {}
                if not probe.get("running"):
                    break
                self.root.after(
                    0,
                    lambda p=probe: self.set_status(
                        f"testando {p.get('done',0)}/{p.get('total',0)}...",
                        "#E65100",
                    ),
                )
            except Exception:
                continue
        self.root.after(0, self._reload_channels)
        self.root.after(0, lambda: self._log("probe", "teste concluido"))

    def _on_select_channel(self, _evt=None) -> None:
        sel = self.channel_list.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._channels):
            return
        self._select_channel(self._channels[idx])

    def _select_channel(self, ch: dict) -> None:
        if self.cast_busy:
            self.set_status("espelhamento em andamento")
            return
        self.pick = dict(ch)
        self.preview_ok = False
        self._update_cast_btn()
        self.preview_lbl.configure(text=f"testando: {ch.get('name')}...", fg="#E65100")
        self._log("info", f"selecionado: {ch.get('name')}")
        threading.Thread(target=self._preview_channel, args=(ch,), daemon=True).start()

    def _preview_channel(self, ch: dict) -> None:
        url = ch.get("url") or ""
        name = ch.get("name") or ""
        try:
            data = api_get(
                "/preview?url="
                + urllib.parse.quote(url, safe="")
                + "&name="
                + urllib.parse.quote(name)
            )
        except Exception as exc:  # noqa: BLE001
            data = {"ok": False, "error": str(exc)}

        def apply() -> None:
            health = data.get("health") or "?"
            if data.get("ok"):
                self.preview_ok = True
                self.preview_lbl.configure(
                    text=f"PREVIEW OK [{health}]\n{ch.get('name')}\nPode espelhar.",
                    fg="#1B5E20",
                )
                self.set_status("pronto para espelhar", "#1B5E20")
                self._log("success", f"preview OK: {ch.get('name')} health={health}")
            else:
                self.preview_ok = False
                err = data.get("error") or "offline"
                self.preview_lbl.configure(
                    text=f"OFFLINE [{health}]\n{ch.get('name')}\n{err}\n(pode tentar mesmo assim)",
                    fg="#B71C1C",
                )
                self.set_status(str(err), "#B71C1C")
                self._log("error", f"preview falhou: {err} health={health}")
                if "globo" in (ch.get("name") or "").lower() and ch.get("url") != GLOBO_RJ["url"]:
                    self._log("info", "sugestao: clique Globo RJ")
            self._update_cast_btn()

        self.root.after(0, apply)

    def _scan_devices(self) -> None:
        try:
            data = api_get("/scan", timeout=40)
            devices = data.get("devices") or []
        except Exception:
            try:
                devices = (api_get("/devices", timeout=10).get("devices") or [])
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self.set_status(f"scan falhou: {exc}"))
                return

        def apply() -> None:
            self.devices = devices
            labels = []
            for d in devices:
                name = d.get("friendlyName") or d.get("name") or "TV"
                host = d.get("host") or ""
                labels.append(f"{name} @ {host}")
            self.device_combo["values"] = labels
            if labels:
                self.device_var.set(labels[0])
                self.set_status(f"{len(labels)} TV(s) na rede", "#1B5E20")
                self._log("scan", f"{len(labels)} dispositivo(s)")
            else:
                self.device_var.set("")
                self.set_status("nenhuma TV Cast achada")
            self._update_cast_btn()

        self.root.after(0, apply)

    def _selected_device(self) -> dict | None:
        label = self.device_var.get()
        if not label or not self.devices:
            return None
        for d in self.devices:
            name = d.get("friendlyName") or d.get("name") or "TV"
            host = d.get("host") or ""
            if f"{name} @ {host}" == label:
                return d
        return self.devices[0]

    def _cast_now(self) -> None:
        if self.cast_busy or not self.pick:
            return
        dev = self._selected_device()
        if not dev:
            self.set_status("selecione a TV")
            return
        self.cast_busy = True
        self._update_cast_btn()
        pick = dict(self.pick)
        mode = "normal" if self.preview_ok else "forcado"
        self._log("started", f"espelhando ({mode}) {pick.get('name')} -> {dev.get('friendlyName')}")
        self.set_status("ESPELHANDO...", "#E65100")
        threading.Thread(target=self._cast_worker, args=(pick, dev), daemon=True).start()

    def _cast_worker(self, pick: dict, dev: dict) -> None:
        try:
            api_post(
                "/cast",
                {
                    "url": pick.get("url"),
                    "title": pick.get("name"),
                    "channelName": pick.get("name"),
                    "deviceName": (dev.get("host") or dev.get("friendlyName") or "philips").lower(),
                    "host": dev.get("host") or "",
                    "deviceLabel": f"{dev.get('friendlyName')} @ {dev.get('host')}",
                },
            )
            ok = False
            err = "timeout"
            for i in range(50):
                time.sleep(1)
                try:
                    st = api_get("/cast_status", timeout=8)
                except Exception:
                    continue
                if st.get("pending"):
                    self.root.after(0, lambda i=i: self.set_status(f"ESPELHANDO... {i+1}s", "#E65100"))
                    continue
                if st.get("ok"):
                    ok = True
                    break
                err = st.get("error") or (st.get("state") or {}).get("message") or "falha"
                break

            def done() -> None:
                self.cast_busy = False
                if ok:
                    self.set_status(f"ESPELHADO OK: {pick.get('name')}", "#1B5E20")
                    self._log("success", f"espelhado: {pick.get('name')}")
                else:
                    self.set_status(f"ERRO: {err}", "#B71C1C")
                    self._log("error", str(err))
                self._update_cast_btn()

            self.root.after(0, done)
        except Exception as exc:  # noqa: BLE001
            def fail() -> None:
                self.cast_busy = False
                self.set_status(f"cast falhou: {exc}", "#B71C1C")
                self._log("error", str(exc))
                self._update_cast_btn()

            self.root.after(0, fail)

    def _tick_dock(self) -> None:
        try:
            if not self._dock_hwnd or not user32.IsWindow(self._dock_hwnd):
                self._dock_hwnd = tk_hwnd(self.root)
                clear_topmost(self._dock_hwnd)

            self._iptv_hwnd = find_iptvnator_hwnd() or self._iptv_hwnd
            if self._iptv_hwnd and not user32.IsWindow(self._iptv_hwnd):
                self._iptv_hwnd = 0

            # dono = IPTVnator => Cast sobe quando clica no app de TV, sem ficar acima de tudo
            if self._iptv_hwnd and self._dock_hwnd and self._owner_set_for != self._iptv_hwnd:
                set_owner(self._dock_hwnd, self._iptv_hwnd)
                clear_topmost(self._dock_hwnd)
                self._owner_set_for = self._iptv_hwnd

            rect = window_rect(self._iptv_hwnd) if self._iptv_hwnd else None
            if rect:
                left, top, right, bottom = rect
                height = max(420, bottom - top)
                x = right - 2
                y = top
                screen_w = int(user32.GetSystemMetrics(0))
                if x + DOCK_W > screen_w - 4:
                    x = max(0, left - DOCK_W + 2)
                anchor = (x, y, DOCK_W, height)
                if anchor != self._last_anchor:
                    self._last_anchor = anchor
                    # repositiona sem forçar topmost; owner cuida do z-order com o IPTVnator
                    ok = move_hwnd(self._dock_hwnd, x, y, DOCK_W, height, after_hwnd=HWND_TOP)
                    if not ok:
                        self.root.geometry(f"{DOCK_W}x{height}+{x}+{y}")

                # se o foco esta no IPTVnator (ou filho dele), sobe o Cast junto
                fg = int(user32.GetForegroundWindow() or 0)
                if fg and self._iptv_hwnd and (
                    fg == self._iptv_hwnd
                    or fg == self._dock_hwnd
                    or user32.IsChild(self._iptv_hwnd, fg)
                ):
                    user32.SetWindowPos(
                        self._dock_hwnd,
                        HWND_TOP,
                        0,
                        0,
                        0,
                        0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
                    )
            else:
                if not self.cast_busy:
                    cur = (self.status.cget("text") or "").lower()
                    if "nao encontrado" not in cur:
                        self.set_status("IPTVnator nao encontrado - abra o app", "#B71C1C")
        except Exception:
            pass
        self.root.after(16, self._tick_dock)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    # espera API
    for _ in range(40):
        try:
            api_get("/health", timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    CastDockApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
