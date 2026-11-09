"""Start the local MLX inference server on demand (macOS, Apple Silicon)."""

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from .llm import LOCAL_BASE_URL, LOCAL_PREFIX

_server_process: Optional[subprocess.Popen] = None
_servers: Dict[str, str] = {}
_processes: Dict[str, subprocess.Popen] = {}
_loaded_bytes: Dict[str, int] = {}
_next_port = 8081
MEMORY_BUDGET = 0.65  # share of physical RAM all local servers together may hold
HEADROOM_BYTES = 3 * 1024**3  # keep this much for the browser and the system


def _is_up(timeout: float = 1.0, base_url: str = LOCAL_BASE_URL) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=timeout) as response:
            return response.getcode() == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def _spawn(model_id: str, port: str) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mlx_lm",
            "server",
            "--model",
            model_id,
            "--port",
            port,
            "--prompt-cache-size",
            "2",
            "--chat-template-args",
            '{"enable_thinking":false}',
            "--log-level",
            "WARNING",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _model_bytes(model_id: str) -> int:
    """Size of the model's weight files in the Hugging Face cache (0 if not downloaded)."""
    from huggingface_hub import scan_cache_dir

    for repo in scan_cache_dir().repos:
        if repo.repo_id == model_id:
            return int(repo.size_on_disk)
    return 0


def _available_bytes() -> int:
    """Memory not pinned by apps: total minus anonymous and wired pages (vm_stat, macOS)."""
    out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
    page = 16384
    pages = {}
    for line in out.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            digits = value.strip().rstrip(".")
            pages[key.strip()] = int(digits) if digits.isdigit() else 0
    total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    pinned = pages.get("Anonymous pages", 0) + pages.get("Pages stored in compressor", 0) + pages.get("Pages wired down", 0)
    return total - pinned * page - HEADROOM_BYTES


def _running_server_bytes() -> int:
    """Weights held by every mlx_lm server on this machine, including other processes."""
    out = subprocess.run(["pgrep", "-fl", "mlx_lm server --model"], capture_output=True, text=True).stdout
    total = 0
    for line in out.splitlines():
        parts = line.split()
        if "--model" in parts:
            total += _model_bytes(parts[parts.index("--model") + 1])
    return total


def _check_memory(model_id: str) -> None:
    """Refuse to load a model that would not fit in memory with headroom."""
    size = _model_bytes(model_id)
    need = size + max(int(0.4 * 1024**3), int(0.08 * size))
    total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    loaded = max(sum(_loaded_bytes.values()), _running_server_bytes())
    if loaded + need > MEMORY_BUDGET * total or loaded + need > _available_bytes():
        raise MemoryError(
            f"refusing to load {model_id}: needs ~{need / 1024**3:.1f} GB, "
            f"{loaded / 1024**3:.1f} GB already loaded, {_available_bytes() / 1024**3:.1f} GB available"
        )


def stop_server(model: str) -> None:
    """Stop the server for one model (no-op if this process did not start it)."""
    model_id = model[len(LOCAL_PREFIX) :] if model.startswith(LOCAL_PREFIX) else model
    process = _processes.pop(model_id, None)
    if process is not None:
        process.terminate()
        process.wait(timeout=15)
    _servers.pop(model_id, None)
    _loaded_bytes.pop(model_id, None)


def shutdown_servers() -> None:
    """Stop every mlx_lm server this process started."""
    for process in list(_processes.values()):
        process.terminate()
    _processes.clear()
    _servers.clear()
    _loaded_bytes.clear()


def server_for(model: str, wait_s: int = 180) -> str:
    """Base URL of a server dedicated to `model`, spawning one on a free port if needed.

    mlx_lm.server holds one model at a time and reloads on every model switch, so each
    model that is used concurrently (planner, reflex scorer) gets its own process.
    """
    global _next_port
    model_id = model[len(LOCAL_PREFIX) :] if model.startswith(LOCAL_PREFIX) else model
    if model_id in _servers:
        return _servers[model_id]
    if not _is_up():
        ensure_local_server(f"{LOCAL_PREFIX}{model_id}", wait_s)
        return LOCAL_BASE_URL
    _check_memory(model_id)
    base_url = f"http://127.0.0.1:{_next_port}/v1"
    _processes[model_id] = _spawn(model_id, str(_next_port))
    _loaded_bytes[model_id] = _model_bytes(model_id)
    _next_port += 1
    for _ in range(wait_s):
        time.sleep(1)
        if _is_up(base_url=base_url):
            _servers[model_id] = base_url
            return base_url
    raise TimeoutError(f"local MLX server for {model_id} did not start")


def list_local_models() -> List[str]:
    """Model ids the local server can serve, prefixed with `local/`; empty when it is down."""
    if not _is_up():
        return []
    import json

    with urllib.request.urlopen(f"{LOCAL_BASE_URL}/models", timeout=2) as response:
        data = json.load(response)
    return [f"{LOCAL_PREFIX}{item['id']}" for item in data.get("data", []) if "mlx" in item["id"].lower()]


def ensure_local_server(model: str, wait_s: int = 120) -> None:
    """Spawn `mlx_lm.server` for `model` if nothing is listening yet."""
    global _server_process
    if not model.startswith(LOCAL_PREFIX) or _is_up():
        return
    model_id = model[len(LOCAL_PREFIX) :]
    _check_memory(model_id)
    port = LOCAL_BASE_URL.rsplit(":", 1)[-1].split("/")[0]
    _server_process = _spawn(model_id, port)
    _processes[model_id] = _server_process
    _servers[model_id] = LOCAL_BASE_URL
    _loaded_bytes[model_id] = _model_bytes(model_id)
    for _ in range(wait_s):
        time.sleep(1)
        if _is_up():
            return
    raise TimeoutError("local MLX server did not start")
