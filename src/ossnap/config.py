import json
import os
import tempfile
from pathlib import Path

from .exceptions import ConfigNotFoundError

CONFIG_DIR = Path.home() / ".ossnap"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "version": 1,
    "github_repo_url": "",
    "ssh_dir": "~/.ssh",
    "scan_dirs": ["~/Documents", "~/Projects"],
    "env_patterns": [".env", ".env.local", ".env.development", ".env.production"],
    "exclude_dirs": ["node_modules", ".git", "venv", "__pycache__", ".venv"],
}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise ConfigNotFoundError("Config not found. Run `ossnap init` first.")
    with open(CONFIG_FILE) as f:
        data = json.load(f)
    # Expand ~ in path fields
    if data.get("ssh_dir"):
        data["ssh_dir"] = str(Path(data["ssh_dir"]).expanduser())
    data["scan_dirs"] = [str(Path(d).expanduser()) for d in data.get("scan_dirs", [])]
    return data


def save_config(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Write atomically via temp file
    fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, CONFIG_FILE)
    except Exception:
        os.unlink(tmp_path)
        raise


def default_config() -> dict:
    return DEFAULT_CONFIG.copy()
