"""One operator file for integration addresses; legacy per-module overrides remain valid."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def local_path():
    return Path(os.getenv("NEF_INTEGRATION_CONFIG") or ROOT / "config" / "integration.local.json")


def section(name):
    path = local_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get(name, {}), dict):
        raise ValueError("Invalid integration configuration")
    return data.get(name, {})
