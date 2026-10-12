#!/usr/bin/env python3
"""Start the spec-kit-app backend (FastAPI) and frontend (Vite) together.

Usage:
    python start.py                 # check deps, then start both servers
    python start.py --no-install    # skip dependency checks/installs
    python start.py --backend-port 8000 --frontend-port 5173

Press Ctrl+C to stop both servers.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

BACKEND_PORT = 8000
FRONTEND_PORT = 5173


def log(tag: str, message: str) -> None:
    print(f"[{tag}] {message}", flush=True)


def stream_output(tag: str, stream) -> None:
    """Read lines from a subprocess pipe and print them with a tag prefix."""
    for raw_line in iter(stream.readline, ""):
        line = raw_line.rstrip()
        if line:
            log(tag, line)
    stream.close()


def backend_env() -> dict:
    """Environment for the backend, preferring a local venv if present."""
    env = os.environ.copy()
    scripts = "Scripts" if os.name == "nt" else "bin"
    venv_python = BACKEND_DIR / ".venv" / scripts / ("python.exe" if os.name == "nt" else "python")
    if venv_python.exists():
        env["VIRTUAL_ENV"] = str(BACKEND_DIR / ".venv")
        env["PATH"] = f"{venv_python.parent}{os.pathsep}{env.get('PATH', '')}"
        return str(venv_python), env
    return sys.executable, env


def backend_deps_installed(python: str) -> bool:
    result = subprocess.run(
        [python, "-c", "import fastapi, uvicorn, sqlmodel"],
        cwd=BACKEND_DIR,
        capture_output=True,
    )
    return result.returncode == 0


def frontend_deps_installed() -> bool:
    return (FRONTEND_DIR / "node_modules").is_dir()


def run(cmd: list[str], cwd: Path) -> None:
    log("setup", f"$ {' '.join(cmd)}  (cwd: {cwd.name})")
    subprocess.run(cmd, cwd=cwd, check=True)


def npm_command() -> str:
    npm = shutil.which("npm")
    if npm:
        return npm
    npm = shutil.which("npm.cmd")
    if npm:
        return npm
    raise RuntimeError("npm not found on PATH — please install Node.js (https://nodejs.org)")


def spawn(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.Popen:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        creationflags=creationflags,
    )


def wait_for_url(url: str, timeout: float = 60.0) -> bool:
    """Poll a URL until it responds or the timeout elapses."""
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Start backend and frontend dev servers.")
    parser.add_argument("--no-install", action="store_true",
                        help="Skip dependency checks and installation")
    parser.add_argument("--backend-port", type=int, default=BACKEND_PORT,
                        help=f"Backend port (default: {BACKEND_PORT})")
    parser.add_argument("--frontend-port", type=int, default=FRONTEND_PORT,
                        help=f"Frontend port (default: {FRONTEND_PORT})")
    args = parser.parse_args()

    for path in (BACKEND_DIR, FRONTEND_DIR):
        if not path.is_dir():
            log("error", f"Missing directory: {path}")
            return 1

    python, env = backend_env()

    if not args.no_install:
        if not backend_deps_installed(python):
            log("setup", "Backend dependencies missing, installing requirements.txt ...")
            run([python, "-m", "pip", "install", "-r", "requirements.txt"], BACKEND_DIR)
        else:
            log("setup", "Backend dependencies OK")
        if not frontend_deps_installed():
            log("setup", "node_modules missing, running npm install ...")
            run([npm_command(), "install"], FRONTEND_DIR)
        else:
            log("setup", "Frontend dependencies OK")

    processes: list[tuple[str, subprocess.Popen]] = []

    backend_cmd = [
        python, "-m", "uvicorn", "main:app",
        "--reload", "--port", str(args.backend_port),
    ]
    backend = spawn(backend_cmd, BACKEND_DIR, env)
    processes.append(("backend", backend))
    threading.Thread(target=stream_output, args=("backend", backend.stdout), daemon=True).start()

    frontend_cmd = [npm_command(), "run", "dev", "--", "--port", str(args.frontend_port)]
    frontend = spawn(frontend_cmd, FRONTEND_DIR)
    processes.append(("frontend", frontend))
    threading.Thread(target=stream_output, args=("frontend", frontend.stdout), daemon=True).start()

    log("setup", "Waiting for backend /health ...")
    if wait_for_url(f"http://localhost:{args.backend_port}/health"):
        log("setup", f"Backend ready  -> http://localhost:{args.backend_port}  (docs: /docs)")
    else:
        log("setup", "Backend did not respond in time — check the [backend] log above")
    log("setup", f"Frontend starting -> http://localhost:{args.frontend_port}")
    log("setup", "Press Ctrl+C to stop both servers.")

    try:
        while True:
            for tag, proc in list(processes):
                if proc.poll() is not None:
                    log(tag, f"process exited with code {proc.returncode}")
                    processes.remove((tag, proc))
            if not processes:
                log("setup", "All processes exited.")
                return 0
            time.sleep(0.5)
    except KeyboardInterrupt:
        log("setup", "Shutting down ...")
    finally:
        for tag, proc in processes:
            if proc.poll() is None:
                proc.terminate()
        deadline = time.time() + 5
        for tag, proc in processes:
            try:
                proc.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                proc.kill()
        log("setup", "Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
