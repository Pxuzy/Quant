from __future__ import annotations

import argparse
import ctypes
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import IO

import uvicorn


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8021
APP_IMPORT = "backend.app.main:app"
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


def project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "backend" / "app" / "main.py").exists():
            return parent
    return Path(__file__).resolve().parents[1]


def api_host() -> str:
    return os.getenv("QUANT_API_HOST", DEFAULT_HOST)


def api_port() -> int:
    return int(os.getenv("QUANT_API_PORT", str(DEFAULT_PORT)))


def storage_dir() -> Path:
    path = project_root() / "storage"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pid_path() -> Path:
    return storage_dir() / f"api-{api_port()}.pid"


def log_path() -> Path:
    return storage_dir() / f"api-{api_port()}.log"


def health_url() -> str:
    return f"http://{api_host()}:{api_port()}/health"


def api_health_state(timeout_seconds: float = 3) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(health_url(), timeout=timeout_seconds) as response:
            return response.status == 200, f"healthy status={response.status}"
    except Exception as exc:
        return False, f"unreachable message={exc}"


def prepare_environment() -> dict[str, str]:
    env: dict[str, str] = {}
    path_value = ""
    for key, value in os.environ.items():
        if key.upper() == "PATH":
            path_value = value if not path_value else path_value
            continue
        env[key] = value
    env["Path" if os.name == "nt" else "PATH"] = path_value
    env.setdefault("PYTHONPATH", str(project_root()))
    return env


def read_pid() -> int | None:
    try:
        raw_value = pid_path().read_text(encoding="utf-8").strip()
        return int(raw_value) if raw_value else None
    except (FileNotFoundError, ValueError):
        return None


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except (OSError, SystemError):
        return False
    return True


def process_command_line(pid: int) -> str:
    if pid <= 0:
        return ""
    if os.name == "nt":
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine",
        ]
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return completed.stdout.strip()

    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    try:
        return proc_cmdline.read_text(encoding="utf-8", errors="replace").replace("\x00", " ").strip()
    except OSError:
        try:
            completed = subprocess.run(
                ["ps", "-p", str(pid), "-o", "args="],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return completed.stdout.strip()


def is_managed_api_process(pid: int) -> bool:
    command_line = process_command_line(pid).lower()
    return APP_IMPORT.lower() in command_line and str(api_port()) in command_line


def is_pid_safe_to_stop(pid: int) -> bool:
    return is_process_running(pid) and is_managed_api_process(pid)


def listening_process_id() -> int | None:
    if os.name != "nt":
        return None
    try:
        completed = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    port_suffix = f":{api_port()}"
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0] != "TCP" or parts[3] != "LISTENING":
            continue
        if parts[1].endswith(port_suffix):
            try:
                return int(parts[4])
            except ValueError:
                return None
    return None


def wait_until_healthy(pid: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if pid > 0 and not is_process_running(pid):
            return False
        healthy, _ = api_health_state(timeout_seconds=2)
        if healthy:
            return True
        time.sleep(0.5)
    return False


def run_foreground() -> None:
    root = project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    uvicorn.run(APP_IMPORT, host=api_host(), port=api_port(), log_level="info")


def recent_log_tail(lines: int = 80) -> str:
    try:
        content = log_path().read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return ""
    return "\n".join(content[-lines:])


def start_background() -> int:
    existing_pid = read_pid()
    if existing_pid is not None and is_process_running(existing_pid):
        healthy, _ = api_health_state()
        if is_managed_api_process(existing_pid):
            return existing_pid
        pid_path().unlink(missing_ok=True)
        if healthy:
            return -1
    elif existing_pid is not None:
        pid_path().unlink(missing_ok=True)

    healthy, _ = api_health_state()
    if healthy:
        pid_path().unlink(missing_ok=True)
        return -1

    owner_pid = listening_process_id()
    if owner_pid is not None:
        raise SystemExit(f"API port {api_port()} is already owned by unmanaged pid={owner_pid}.")

    log_file: IO[bytes] | None = None
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        APP_IMPORT,
        "--host",
        api_host(),
        "--port",
        str(api_port()),
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    try:
        log_file = log_path().open("ab")
        process = subprocess.Popen(
            command,
            cwd=project_root(),
            env=prepare_environment(),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            close_fds=os.name != "nt",
        )
    finally:
        if log_file is not None:
            log_file.close()
    pid_path().write_text(str(process.pid), encoding="utf-8")
    return process.pid


def stop_background() -> bool:
    pid = read_pid()
    if pid is None:
        return False
    if not is_process_running(pid):
        pid_path().unlink(missing_ok=True)
        return False
    if not is_pid_safe_to_stop(pid):
        pid_path().unlink(missing_ok=True)
        return False

    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
    else:
        os.kill(pid, signal.SIGTERM)

    pid_path().unlink(missing_ok=True)
    return True


def status_text() -> str:
    pid = read_pid()
    healthy, api_state = api_health_state()
    if healthy:
        if pid is not None and is_process_running(pid) and is_managed_api_process(pid):
            process_state = f"running pid={pid}"
        else:
            if pid is not None:
                pid_path().unlink(missing_ok=True)
            owner_pid = listening_process_id()
            if owner_pid is not None:
                process_state = f"running pid={owner_pid} (unmanaged)"
            else:
                process_state = "running"
    else:
        process_state = "stopped"
    return f"{process_state}; {api_state}; url={health_url()}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Quant API server.")
    parser.add_argument("command", nargs="?", choices=("run", "start", "stop", "status"), default="run")
    parser.add_argument("--wait", type=float, default=30.0, help="Seconds to wait for health after start.")
    args = parser.parse_args()

    if args.command == "run":
        run_foreground()
        return
    if args.command == "start":
        pid = start_background()
        if not wait_until_healthy(pid, args.wait):
            log_tail = recent_log_tail()
            process_state = (
                "served by an existing process"
                if pid <= 0
                else "still running"
                if is_process_running(pid)
                else "exited before health check"
            )
            detail = (
                f"API server started with pid {pid}, but health check did not pass "
                f"({process_state}). {status_text()}"
            )
            if log_tail:
                detail = f"{detail}\n\nRecent log:\n{log_tail}"
            raise SystemExit(detail)
        if pid > 0:
            print(f"API server started: pid={pid} url={health_url()}", flush=True)
        else:
            print(f"API server already healthy: url={health_url()}", flush=True)
        return
    if args.command == "stop":
        stopped = stop_background()
        print("API server stopped." if stopped else "API server was not running.", flush=True)
        return
    if args.command == "status":
        print(status_text(), flush=True)


if __name__ == "__main__":
    main()
