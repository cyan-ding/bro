"""Start the local MLX inference server on demand (macOS, Apple Silicon)."""

import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import List, Optional

from .llm import LOCAL_BASE_URL, LOCAL_PREFIX

_server_process: Optional[subprocess.Popen] = None


def _is_up(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"{LOCAL_BASE_URL}/models", timeout=timeout) as response:
            return response.getcode() == 200
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


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
    port = LOCAL_BASE_URL.rsplit(":", 1)[-1].split("/")[0]
    _server_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "mlx_lm",
            "server",
            "--model",
            model[len(LOCAL_PREFIX) :],
            "--port",
            port,
            "--prompt-cache-size",
            "8",
            "--chat-template-args",
            '{"enable_thinking":false}',
            "--log-level",
            "WARNING",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(wait_s):
        time.sleep(1)
        if _is_up():
            return
    raise TimeoutError("local MLX server did not start")
