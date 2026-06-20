#!/usr/bin/env python
"""Quant Launcher — simple tkinter window to start/stop API + Web."""

import json, os, subprocess, sys, threading, time, urllib.request
from pathlib import Path
from tkinter import Tk, Frame, Label, Button, Text, Scrollbar, messagebox, BOTH, LEFT, RIGHT, X, Y, END, DISABLED, NORMAL

# ── Paths ──────────────────────────────────────────────────────────

def _root() -> Path:
    for p in Path(__file__).resolve().parents:
        if (p / "apps" / "api" / "main.py").exists():
            return p
    return Path(__file__).resolve().parents[1]

ROOT   = _root()
PYTHON = str(ROOT / "quant" / ".venv" / "Scripts" / "python.exe")
SCRIPT = str(ROOT / "quant" / "scripts" / "run_api_server.py")
WEBDIR = str(ROOT / "apps" / "web")
CFG    = ROOT / "storage" / "launcher-config.json"

# ── Config ─────────────────────────────────────────────────────────

def _load():
    try: return json.loads(CFG.read_text(encoding="utf-8"))
    except: return {}
def _save(d): CFG.write_text(json.dumps(d, indent=2), encoding="utf-8")

cfg = _load()
API_PORT  = cfg.get("api_port", 8021)
WEB_PORT  = cfg.get("web_port", 5175)

# ── Helpers ────────────────────────────────────────────────────────

def _health(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except: return False

def _log(*args):
    text = " ".join(str(a) for a in args) + "\n"
    if _log.widget:
        _log.widget.after(0, lambda: _append(text))
    print(text, end="")
_log.widget = None

def _append(text):
    w = _log.widget
    if w is None: return
    w.configure(state=NORMAL)
    w.insert(END, text)
    w.see(END)
    w.configure(state=DISABLED)

# ── Service management ─────────────────────────────────────────────

_api_proc = None
_web_proc = None
_web_log_thread = None

def _web_ready(timeout=3):
    page_url = f"http://127.0.0.1:{WEB_PORT}/data-system/overview"
    entry_url = f"http://127.0.0.1:{WEB_PORT}/src/main.tsx"
    if not _health(page_url, timeout=timeout):
        return False
    try:
        with urllib.request.urlopen(entry_url, timeout=timeout) as r:
            body = r.read(4096).decode("utf-8", errors="replace")
            content_type = r.headers.get("Content-Type", "")
            if r.status < 200 or r.status >= 400:
                return False
            if "text/html" in content_type and (
                "Internal Server Error" in body or "spawn EPERM" in body or "ErrorOverlay" in body
            ):
                return False
            return True
    except Exception:
        return False

def start_api():
    global _api_proc
    env = os.environ.copy()
    env["QUANT_API_PORT"] = str(API_PORT)
    env["PYTHONPATH"] = str(ROOT)
    _log(">>> Starting API on port", API_PORT)
    try:
        # run_api_server.py start --wait is BLOCKING (waits for health)
        # so this must run in a thread
        r = subprocess.run(
            [PYTHON, SCRIPT, "start", "--wait", "30"],
            cwd=str(ROOT), env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=45,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        if r.returncode == 0:
            _log("API: started —", r.stdout.strip())
        else:
            _log("API: FAILED —", (r.stderr or r.stdout or f"exit {r.returncode}").strip())
    except subprocess.TimeoutExpired:
        _log("API: TIMEOUT after 45s")
    except Exception as e:
        _log("API: ERROR —", e)

def stop_api():
    _log(">>> Stopping API")
    env = os.environ.copy()
    env["QUANT_API_PORT"] = str(API_PORT)
    env["PYTHONPATH"] = str(ROOT)
    subprocess.run(
        [PYTHON, SCRIPT, "stop"], cwd=str(ROOT), env=env,
        capture_output=True, timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    _log("API: stopped")

def _stream_web_output(proc):
    if proc.stdout is None:
        return
    for line in proc.stdout:
        _log("[web]", line.rstrip())

def start_web():
    global _web_proc, _web_log_thread
    if not (Path(WEBDIR) / "node_modules").exists():
        _log("WEB: node_modules missing — run: cd apps/web && npm install")
        return
    _log(">>> Starting Web on port", WEB_PORT)
    env = os.environ.copy()
    env["VITE_API_PROXY_TARGET"] = f"http://127.0.0.1:{API_PORT}"
    env["VITE_DEV_SERVER_PORT"] = str(WEB_PORT)
    try:
        _web_proc = subprocess.Popen(
            ["cmd.exe", "/c",
             f"npm run dev -- --host 127.0.0.1 --port {WEB_PORT} --strictPort"],
            cwd=WEBDIR, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        _log("WEB: spawned pid", _web_proc.pid)
        _web_log_thread = threading.Thread(target=_stream_web_output, args=(_web_proc,), daemon=True)
        _web_log_thread.start()
    except Exception as e:
        _log("WEB: ERROR —", e)

def stop_web():
    global _web_proc
    if _web_proc is None:
        return
    _log(">>> Stopping Web")
    pid = _web_proc.pid
    if os.name == "nt" and pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    else:
        _web_proc.terminate()
    _web_proc = None
    _log("Web: stopped")

def read_web_output():
    return

# ── UI ─────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        self.root = Tk()
        self.root.title("Quant Launcher")
        self.root.geometry("860x620")
        self.root.minsize(500, 350)

        # ── Top control bar ──
        bar = Frame(self.root, bg="#e8e8e8", height=48)
        bar.pack(fill=X)
        bar.pack_propagate(False)

        self.api_led = Label(bar, text=" ● ", fg="#cc0000", bg="#e8e8e8", font=("", 14))
        self.api_led.pack(side=LEFT, padx=(12, 2))

        Label(bar, text="API", bg="#e8e8e8", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 8))

        self.btn_api_start = Button(bar, text="Start", command=self._start_api,
                                    bg="#27ae60", fg="white", relief="flat",
                                    font=("Segoe UI", 9), padx=12, pady=2)
        self.btn_api_start.pack(side=LEFT, padx=2)

        self.btn_api_stop = Button(bar, text="Stop", command=self._stop_api,
                                   bg="#e74c3c", fg="white", relief="flat",
                                   font=("Segoe UI", 9), padx=12, pady=2,
                                   state=DISABLED)
        self.btn_api_stop.pack(side=LEFT, padx=2)

        # separator
        Label(bar, text="  │  ", bg="#e8e8e8", fg="#ccc").pack(side=LEFT, padx=(12, 8))

        self.web_led = Label(bar, text=" ● ", fg="#cc0000", bg="#e8e8e8", font=("", 14))
        self.web_led.pack(side=LEFT, padx=(0, 2))

        Label(bar, text="Web", bg="#e8e8e8", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=(0, 8))

        self.btn_web_start = Button(bar, text="Start", command=self._start_web,
                                    bg="#27ae60", fg="white", relief="flat",
                                    font=("Segoe UI", 9), padx=12, pady=2)
        self.btn_web_start.pack(side=LEFT, padx=2)

        self.btn_web_stop = Button(bar, text="Stop", command=self._stop_web,
                                   bg="#e74c3c", fg="white", relief="flat",
                                   font=("Segoe UI", 9), padx=12, pady=2,
                                   state=DISABLED)
        self.btn_web_stop.pack(side=LEFT, padx=2)

        # All start/stop
        Label(bar, text="  │  ", bg="#e8e8e8", fg="#ccc").pack(side=LEFT, padx=(12, 8))
        Button(bar, text="Start All", command=self._start_all,
               bg="#555", fg="white", relief="flat",
               font=("Segoe UI", 8), padx=10, pady=2).pack(side=LEFT, padx=2)
        Button(bar, text="Stop All", command=self._stop_all,
               bg="#555", fg="white", relief="flat",
               font=("Segoe UI", 8), padx=10, pady=2).pack(side=LEFT, padx=2)

        # ── Log area ──
        log_frame = Frame(self.root, bg="#1a1a2e")
        log_frame.pack(fill=BOTH, expand=True)

        self.log_text = Text(log_frame, wrap="word", state=DISABLED,
                             font=("Consolas", 9), bg="#1a1a2e", fg="#d0d0d0",
                             relief="flat", borderwidth=0, padx=8, pady=6,
                             insertbackground="#d0d0d0")
        scroll = Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

        _log.widget = self.log_text
        _log("Quant Launcher ready.")
        _log(f"API: http://127.0.0.1:{API_PORT}/health")
        _log(f"Web: http://127.0.0.1:{WEB_PORT}")
        _log("─" * 50)

        # ── Status bar ──
        self.status = Label(self.root, text="API: Stopped  │  Web: Stopped",
                            bg="#ddd", fg="#555", anchor="w",
                            font=("Segoe UI", 8), padx=8, pady=2)
        self.status.pack(fill=X, side="bottom")

        # ── Polling ──
        self.root.after(2000, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

    # ── Actions ──

    def _start_api(self):
        self.btn_api_start.configure(state=DISABLED)
        self.api_led.configure(fg="#f39c12", text=" ◉ ")
        self._set_status()
        threading.Thread(target=self._start_api_bg, daemon=True).start()

    def _start_api_bg(self):
        start_api()
        self.root.after(0, self._refresh_api_ui)

    def _stop_api(self):
        self.btn_api_stop.configure(state=DISABLED)
        threading.Thread(target=lambda: (stop_api(), self.root.after(0, self._refresh_api_ui)), daemon=True).start()

    def _refresh_api_ui(self):
        ok = _health(f"http://127.0.0.1:{API_PORT}/health")
        if ok:
            self.api_led.configure(fg="#27ae60", text=" ● ")
            self.btn_api_start.configure(state=DISABLED)
            self.btn_api_stop.configure(state=NORMAL)
        else:
            self.api_led.configure(fg="#cc0000", text=" ● ")
            self.btn_api_start.configure(state=NORMAL)
            self.btn_api_stop.configure(state=DISABLED)
        self._set_status()

    def _start_web(self):
        self.btn_web_start.configure(state=DISABLED)
        self.web_led.configure(fg="#f39c12", text=" ◉ ")
        self._set_status()
        threading.Thread(target=lambda: (start_web(), self.root.after(0, self._refresh_web_ui)), daemon=True).start()

    def _stop_web(self):
        self.btn_web_stop.configure(state=DISABLED)
        threading.Thread(target=lambda: (stop_web(), self.root.after(0, self._refresh_web_ui)), daemon=True).start()

    def _refresh_web_ui(self):
        global _web_proc
        # Check if process exited unexpectedly
        if _web_proc and _web_proc.poll() is not None:
            _log("WEB: process exited with code", _web_proc.returncode)
            _web_proc = None
        ok = _web_ready()
        if ok:
            self.web_led.configure(fg="#27ae60", text=" ● ")
            self.btn_web_start.configure(state=DISABLED)
            self.btn_web_stop.configure(state=NORMAL)
        elif _web_proc is not None:
            self.web_led.configure(fg="#f39c12", text=" ◉ ")
            self.btn_web_start.configure(state=DISABLED)
            self.btn_web_stop.configure(state=NORMAL)
        else:
            self.web_led.configure(fg="#cc0000", text=" ● ")
            self.btn_web_start.configure(state=NORMAL)
            self.btn_web_stop.configure(state=DISABLED)
        self._set_status()

    def _start_all(self):
        self._start_api()
        self.root.after(4000, self._start_web)

    def _stop_all(self):
        self._stop_web()
        self._stop_api()

    def _set_status(self):
        api_ok = _health(f"http://127.0.0.1:{API_PORT}/health")
        web_ok = _web_ready()
        a = "Running" if api_ok else "Stopped"
        w = "Running" if web_ok else "Stopped"
        self.status.configure(text=f"API: {a}  │  Web: {w}    (F5 refresh)")

    # ── Polling ──

    def _poll(self):
        if not self.root.winfo_exists():
            return
        # Read web output
        read_web_output()
        # Refresh UI state
        self._refresh_api_ui()
        self._refresh_web_ui()
        # Load API log tail
        try:
            api_log = ROOT / "storage" / f"api-{API_PORT}.log"
            if api_log.exists():
                # Just append last 2 lines if they're new
                pass  # API controller writes to file; we could tail it here
        except: pass
        self.root.after(2000, self._poll)

    # ── Quit ──

    def _quit(self):
        _log("Shutting down…")
        stop_web()
        stop_api()
        _save({"api_port": API_PORT, "web_port": WEB_PORT})
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
