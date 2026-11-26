"""Start the local MLX inference server on demand (macOS, Apple Silicon)."""

import os
import platform
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel
from tqdm.auto import tqdm

LOCAL_PREFIX = "local/"
QWEN_MODEL = "mlx-community/Qwen3.6-35B-A3B-4bit"
LOCAL_BASE_URL = os.environ.get("BRO_LOCAL_BASE_URL", "http://127.0.0.1:8080/v1")
SPLASH_BASE_URL = "http://127.0.0.1:8001/v1"
# Builds that an engine with a memory cap (Splash) can run when the full model does not fit.
LOW_MEMORY_BUILDS: Dict[str, str] = {
    QWEN_MODEL: "unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q2_K_XL",
}

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
        start_new_session=True,
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
        _terminate(process)
    _servers.pop(model_id, None)
    _loaded_bytes.pop(model_id, None)


def shutdown_servers() -> None:
    """Stop every mlx_lm server this process started."""
    for process in list(_processes.values()):
        _terminate(process)
    _processes.clear()
    _servers.clear()
    _loaded_bytes.clear()


def _spawn_splash(build: str, served_name: str, cap_gb: int) -> subprocess.Popen:
    log = open(Path.home() / ".bro" / "splash.log", "w")
    return subprocess.Popen(
        [
            "splash", "serve", "--model", build, "--max-memory", f"{cap_gb}G", "--idle-release", "5m",
            "--served-model-name", served_name, "--announce-served-name", "--language-only",
            "--port", SPLASH_BASE_URL.rsplit(":", 1)[-1].split("/")[0], "--no-webui",
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _terminate(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)


def server_for(model: str, wait_s: int = 180) -> str:
    """Base URL of a server dedicated to `model`, spawning one on a free port if needed.

    mlx_lm.server holds one model at a time and reloads on every model switch, so each
    model that is used concurrently (planner, reflex scorer) gets its own process.
    """
    global _next_port
    model_id = model[len(LOCAL_PREFIX) :] if model.startswith(LOCAL_PREFIX) else model
    if model_id in _servers:
        return _servers[model_id]
    if os.environ.get("BRO_LOCAL_EXTERNAL"):
        # The server at BRO_LOCAL_BASE_URL is managed by someone else (e.g. Splash): never spawn.
        _servers[model_id] = LOCAL_BASE_URL
        return LOCAL_BASE_URL
    if not _is_up():
        ensure_local_server(f"{LOCAL_PREFIX}{model_id}", wait_s)
        return _servers.get(model_id, LOCAL_BASE_URL)
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


class _WeightIndex(BaseModel):
    weight_map: Dict[str, str]


def _has_all_weights(snapshot: Path) -> bool:
    """True when every weight file is present, so a half-finished download is not offered."""
    index = snapshot / "model.safetensors.index.json"
    if not index.exists():
        return (snapshot / "model.safetensors").exists()
    files = set(_WeightIndex.model_validate_json(index.read_text()).weight_map.values())
    return (snapshot / "config.json").exists() and all((snapshot / name).exists() for name in files)


def _cached_mlx_model_ids() -> List[str]:
    """MLX repos fully downloaded to the Hugging Face cache, so the picker works before a server starts."""
    try:
        from huggingface_hub import scan_cache_dir
    except ImportError:
        return []
    ids: List[str] = []
    for repo in scan_cache_dir().repos:
        if "mlx" not in repo.repo_id.lower() or repo.size_on_disk < 1_000_000_000:
            continue
        if any(_has_all_weights(revision.snapshot_path) for revision in repo.revisions):
            ids.append(repo.repo_id)
    return ids


def list_local_models() -> List[str]:
    """Model ids the local server can serve, prefixed with `local/`.

    Includes cached MLX weights even when nothing is listening yet. A run starts the server.
    """
    found = set(_cached_mlx_model_ids())
    if _is_up():
        import json

        try:
            with urllib.request.urlopen(f"{LOCAL_BASE_URL}/models", timeout=2) as response:
                data = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            data = {}
        for item in data.get("data", []):
            model_id = item.get("id", "")
            if "mlx" in model_id.lower():
                found.add(model_id)
    return [f"{LOCAL_PREFIX}{model_id}" for model_id in sorted(found)]


def ensure_local_server(model: str, wait_s: int = 120) -> None:
    """Spawn `mlx_lm.server` for `model` if nothing is listening yet."""
    global _server_process
    if not model.startswith(LOCAL_PREFIX) or _is_up():
        return
    model_id = model[len(LOCAL_PREFIX) :]
    try:
        _check_memory(model_id)
    except MemoryError:
        if model_id not in LOW_MEMORY_BUILDS or shutil.which("splash") is None:
            raise
        _start_low_memory(model_id, wait_s)
        return
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


def _start_low_memory(model_id: str, wait_s: int) -> None:
    """Serve a 2-bit build of `model_id` through Splash with a cap sized to the free memory.

    Measured on an M4 Max: the 2-bit Qwen3.6-35B-A3B matched the 4-bit on accuracy at a 12 GB cap
    and ran at near full speed; smaller caps stream experts from SSD and trade speed for memory.
    """
    # 10 GB was the measured sweet spot on a 36 GB M4 Max with ~16 GB of other apps open:
    # same accuracy as higher caps, half the memory compression, ~10% slower tasks.
    cap_gb = int(os.environ.get("BRO_SPLASH_CAP_GB", 0)) or max(8, min(10, int(_available_bytes() / 1024**3) - 1))
    if _is_up(base_url=SPLASH_BASE_URL):
        _servers[model_id] = SPLASH_BASE_URL
        return
    _processes[model_id] = _spawn_splash(LOW_MEMORY_BUILDS[model_id], model_id, cap_gb)
    _servers[model_id] = SPLASH_BASE_URL
    _loaded_bytes[model_id] = cap_gb * 1024**3
    for _ in range(wait_s * 3):
        time.sleep(1)
        if _is_up(base_url=SPLASH_BASE_URL):
            return
    raise TimeoutError("Splash did not start (see ~/.bro/splash.log)")


class QwenStatus(BaseModel):
    model: str
    path: Optional[str] = None
    downloading: bool = False
    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None
    supported: bool
    fits: bool
    ram_gb: int
    error: Optional[str] = None


_qwen_total_bytes: Optional[int] = None
_qwen_download: Optional[threading.Thread] = None
_qwen_error: Optional[str] = None
_qwen_bars: List[tqdm] = []


class _TrackedBar(tqdm):
    """Progress bar that remembers itself, since Xet writes the weight files only near the end."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        _qwen_bars.append(self)


def _qwen_cache_dir() -> Path:
    from huggingface_hub.constants import HF_HUB_CACHE

    return Path(HF_HUB_CACHE) / f"models--{QWEN_MODEL.replace('/', '--')}"


def _qwen_size() -> Optional[int]:
    """Total size of the Qwen weights on Hugging Face, fetched once (None when offline)."""
    global _qwen_total_bytes
    if _qwen_total_bytes is None:
        from huggingface_hub import HfApi

        try:
            info = HfApi().model_info(QWEN_MODEL, files_metadata=True)
        except Exception:
            return None
        _qwen_total_bytes = sum(file.size or 0 for file in info.siblings or [])
    return _qwen_total_bytes


def qwen_status() -> QwenStatus:
    """Where the local Qwen weights are, how much is downloaded, and whether this Mac can run them."""
    total_ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    total = _qwen_size()
    blobs = _qwen_cache_dir() / "blobs"
    files = list(blobs.iterdir()) if blobs.is_dir() else []
    downloaded = sum(file.stat().st_size for file in files)
    downloading = _qwen_download is not None and _qwen_download.is_alive()
    if downloading:
        downloaded = max([int(bar.n) for bar in _qwen_bars if bar.unit == "B"] + [0])
    complete = (
        bool(files)
        and not downloading
        and not any(file.name.endswith(".incomplete") for file in files)
        and (total is None or downloaded >= total)
    )
    path = None
    if complete:
        from huggingface_hub import snapshot_download

        path = snapshot_download(QWEN_MODEL, local_files_only=True)
    size = total or downloaded
    need = size + max(int(0.4 * 1024**3), int(0.08 * size))
    return QwenStatus(
        model=f"{LOCAL_PREFIX}{QWEN_MODEL}",
        path=path,
        downloading=downloading,
        downloaded_bytes=downloaded,
        total_bytes=total,
        supported=platform.system() == "Darwin" and platform.machine() == "arm64",
        fits=size > 0 and need <= MEMORY_BUDGET * total_ram,
        ram_gb=round(total_ram / 1024**3),
        error=_qwen_error,
    )


def _download_qwen() -> None:
    global _qwen_error
    from huggingface_hub import snapshot_download

    try:
        snapshot_download(QWEN_MODEL, tqdm_class=_TrackedBar)
    except Exception as error:
        _qwen_error = str(error)


def start_qwen_download() -> None:
    """Download the Qwen weights into the Hugging Face cache in the background."""
    global _qwen_download, _qwen_error
    if _qwen_download is not None and _qwen_download.is_alive():
        return
    _qwen_error = None
    _qwen_bars.clear()
    _qwen_download = threading.Thread(target=_download_qwen, daemon=True)
    _qwen_download.start()
