#!/usr/bin/env python3
"""
Launcher unico do IPTV Cast Companion.

- uma instancia por vez (lock em arquivo)
- sobe API/UI so se as portas nao estiverem saudaveis
- abre Chrome em modo app (perfil proprio)
- ao fechar a janela do Chrome, encerra o companion e libera as portas
"""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API_PORT = 8769
FRONTEND_PORT = 3000
UI_URL = f"http://127.0.0.1:{FRONTEND_PORT}/"
LOGS_DIR = ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOCK_PATH = LOGS_DIR / "iptv_app.lock"
PID_PATH = LOGS_DIR / "companion.pid"
CHROME_PROFILE = ROOT / "chrome-app-profile"
COMPANION = ROOT / "iptvnator_companion.py"

_lock_fh = None
_mutex_handle = None
_companion_proc: subprocess.Popen | None = None
_WINDOWS_JOB_OBJECT = None


def enable_windows_job_object_cleanup() -> None:
    """Windows Job Object para matar todos os filhos (Chrome, Companion, Node, MPV) ao sair."""
    global _WINDOWS_JOB_OBJECT
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryLimit", ctypes.c_size_t),
                ("PeakJobMemoryLimit", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

        job = kernel32.CreateJobObjectW(None, None)
        if job:
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
                kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())
                _WINDOWS_JOB_OBJECT = job
    except Exception:
        pass


enable_windows_job_object_cleanup()


def python_exe() -> str:
    """Python do venv Hermes (tem as deps). Stub uv e normal ver 2 processos."""
    hermes = (
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "hermes"
        / "hermes-agent"
        / "venv"
        / "Scripts"
        / "python.exe"
    )
    if hermes.exists():
        return str(hermes)
    return sys.executable


def chrome_exe() -> Path | None:
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    for p in (
        pf / "Google" / "Chrome" / "Application" / "chrome.exe",
        pf86 / "Google" / "Chrome" / "Application" / "chrome.exe",
        local / "Google" / "Chrome" / "Application" / "chrome.exe",
    ):
        if p.exists():
            return p
    return None


def api_ok() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{API_PORT}/health", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return bool(data.get("ok"))
    except Exception:
        return False


def frontend_ok() -> bool:
    try:
        with urllib.request.urlopen(UI_URL, timeout=2) as resp:
            return int(getattr(resp, "status", 200) or 200) < 500
    except Exception:
        return False


def port_pids(port: int) -> list[int]:
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue "
                f"| Select-Object -ExpandProperty OwningProcess -Unique",
            ],
            text=True,
            errors="ignore",
            timeout=15,
        )
    except Exception:
        return []
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pid = int(line)
            if pid > 0:
                pids.append(pid)
    return pids


def kill_pid(pid: int) -> None:
    if pid <= 0:
        return
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)


def free_ports(*ports: int) -> None:
    me = os.getpid()
    for port in ports:
        for pid in port_pids(port):
            if pid != me:
                print(f"INFO: liberando porta {port} (pid={pid})", flush=True)
                kill_pid(pid)
    if PID_PATH.exists():
        try:
            old = int(PID_PATH.read_text(encoding="utf-8").strip())
            if old != me:
                kill_pid(old)
        except Exception:
            pass
        try:
            PID_PATH.unlink(missing_ok=True)
        except Exception:
            pass


def chrome_profile_pids() -> list[int]:
    marker = str(CHROME_PROFILE).replace("'", "''")
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" -ErrorAction SilentlyContinue "
                f"| Where-Object {{ $_.CommandLine -like '*{marker}*' }} "
                "| Select-Object -ExpandProperty ProcessId",
            ],
            text=True,
            errors="ignore",
            timeout=20,
        )
    except Exception:
        return []
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def try_acquire_lock() -> bool:
    """Mutex nomeado do Windows + arquivo de lock (uma instancia por vez)."""
    global _lock_fh, _mutex_handle
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ERROR_ALREADY_EXISTS = 183
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, "Local\\IPTVCastCompanionSingleInstance")
    if not handle:
        return False
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _mutex_handle = handle

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK_PATH, "a+", encoding="utf-8")
    try:
        import msvcrt

        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        fh.close()
        kernel32.CloseHandle(handle)
        _mutex_handle = None
        return False
    except Exception:
        fh.close()
        kernel32.CloseHandle(handle)
        _mutex_handle = None
        return False
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()))
    fh.flush()
    _lock_fh = fh
    return True


def release_lock() -> None:
    global _lock_fh, _mutex_handle
    if _lock_fh is not None:
        try:
            import msvcrt

            _lock_fh.seek(0)
            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        try:
            _lock_fh.close()
        except Exception:
            pass
        _lock_fh = None
    if _mutex_handle is not None:
        try:
            import ctypes

            ctypes.windll.kernel32.CloseHandle(_mutex_handle)
        except Exception:
            pass
        _mutex_handle = None
    try:
        LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def focus_existing_chrome() -> bool:
    """Reabre/foca a janela do app no mesmo perfil (Chrome nao cria segunda instancia)."""
    chrome = chrome_exe()
    if not chrome:
        return False
    if not chrome_profile_pids() and not (api_ok() and frontend_ok()):
        return False
    prepare_chrome_profile()
    subprocess.Popen(
        [
            str(chrome),
            f"--user-data-dir={CHROME_PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-background-mode",
            f"--app={UI_URL}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("OK: ja havia uma instancia; focando o Chrome", flush=True)
    return True


def start_companion() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["IPTV_NO_BROWSER"] = "1"
    # launcher ja liberou portas; companion sobe do zero (sem soft-start)
    env["IPTV_FORCE_RESTART"] = "1"
    return subprocess.Popen(
        [python_exe(), str(COMPANION)],
        cwd=str(ROOT),
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


def wait_ready(timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if api_ok() and frontend_ok():
            return True
        time.sleep(1.0)
    return False


def prepare_chrome_profile() -> None:
    """Perfil dedicado sem modo segundo plano (fecha de verdade ao fechar a janela)."""
    CHROME_PROFILE.mkdir(parents=True, exist_ok=True)
    default_dir = CHROME_PROFILE / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)
    local_state = CHROME_PROFILE / "Local State"
    prefs_path = default_dir / "Preferences"
    local = {}
    if local_state.exists():
        try:
            local = json.loads(local_state.read_text(encoding="utf-8"))
        except Exception:
            local = {}
    local.setdefault("browser", {})
    local["browser"]["enabled_labs_experiments"] = local["browser"].get("enabled_labs_experiments") or []
    local["background_mode"] = {"enabled": False}
    local_state.write_text(json.dumps(local, ensure_ascii=False), encoding="utf-8")
    prefs = {}
    if prefs_path.exists():
        try:
            prefs = json.loads(prefs_path.read_text(encoding="utf-8"))
        except Exception:
            prefs = {}
    prefs.setdefault("browser", {})
    prefs["browser"]["background_mode_enabled"] = False
    prefs.setdefault("profile", {})
    prefs["profile"]["exit_type"] = "Normal"
    prefs_path.write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")


def open_chrome_app() -> None:
    chrome = chrome_exe()
    if not chrome:
        raise RuntimeError("Chrome nao encontrado")
    prepare_chrome_profile()
    subprocess.Popen(
        [
            str(chrome),
            f"--user-data-dir={CHROME_PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-background-mode",
            "--disable-background-networking",
            "--disable-features=TranslateUI",
            f"--app={UI_URL}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"OK: Chrome app -> {UI_URL}", flush=True)


def wait_chrome_closed(grace: float = 8.0) -> None:
    """Espera o Chrome do perfil abrir e depois fechar por completo."""
    deadline = time.time() + grace
    while time.time() < deadline and not chrome_profile_pids():
        time.sleep(0.4)
    if not chrome_profile_pids():
        print("WARN: Chrome do app nao detectado; encerrando mesmo assim", flush=True)
        return
    print("INFO: app aberto; ao fechar a janela o companion libera as portas", flush=True)
    while chrome_profile_pids():
        time.sleep(1.2)


def shutdown_all() -> None:
    global _companion_proc
    print("INFO: fechando companion e liberando portas...", flush=True)
    if _companion_proc is not None and _companion_proc.poll() is None:
        try:
            _companion_proc.terminate()
            try:
                _companion_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _companion_proc.kill()
        except Exception:
            pass
    free_ports(API_PORT, FRONTEND_PORT)
    # garante Chrome do perfil morto (evita zombie do perfil)
    for pid in chrome_profile_pids():
        kill_pid(pid)
    _companion_proc = None
    release_lock()
    print("OK: portas liberadas", flush=True)


def main() -> int:
    global _companion_proc

    if not COMPANION.exists():
        print(f"ERRO: companion ausente: {COMPANION}", flush=True)
        return 1

    if not try_acquire_lock():
        # segunda abertura: so foca a janela existente e sai
        if focus_existing_chrome():
            return 0
        # API pode ainda estar subindo: tenta abrir o Chrome mesmo assim
        try:
            open_chrome_app()
            return 0
        except Exception:
            print("ERRO: outra instancia parece travada; tente de novo em alguns segundos", flush=True)
            return 1

    atexit.register(shutdown_all)

    # se portas estao saudaveis de uma sessao anterior orfa, limpa antes
    if api_ok() or frontend_ok() or port_pids(API_PORT) or port_pids(FRONTEND_PORT):
        print("INFO: portas em uso; liberando antes de abrir instancia unica", flush=True)
        free_ports(API_PORT, FRONTEND_PORT)
        time.sleep(1.0)

    print("INFO: iniciando companion...", flush=True)
    _companion_proc = start_companion()
    if not wait_ready(90.0):
        print("ERRO: API/UI nao subiram a tempo", flush=True)
        shutdown_all()
        return 1

    try:
        open_chrome_app()
    except Exception as exc:  # noqa: BLE001
        print(f"ERRO: Chrome: {exc}", flush=True)
        shutdown_all()
        return 1

    wait_chrome_closed()
    shutdown_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
