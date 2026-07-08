from __future__ import annotations

import hashlib
import json
from pathlib import Path


CONFIG_DIR = Path(__file__).resolve().parent


def load_config(name: str) -> dict:
    path = CONFIG_DIR / name
    if path.suffix == "":
        path = path.with_suffix(".yaml")
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path.name}")
    return _parse_simple_yaml(path.read_text(encoding="utf-8"))


def load_backtest_config() -> dict:
    return load_config("backtest.yaml")


def load_risk_config() -> dict:
    return load_config("risk.yaml")


def load_universe_config() -> dict:
    return load_config("universe.yaml")


def load_research_config() -> dict:
    return {
        "backtest": load_backtest_config(),
        "risk": load_risk_config(),
        "universe": load_universe_config(),
    }


def build_config_hash(config: dict) -> str:
    raw = json.dumps(config, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _parse_simple_yaml(text: str) -> dict:
    result: dict[str, object] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"invalid config line: {raw_line}")
        key, value = line.split(":", 1)
        result[key.strip()] = _parse_scalar(value.strip())
    return result


def _parse_scalar(value: str) -> object:
    if value == "":
        return ""
    lowered = value.lower()
    if lowered in {"null", "none"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item.strip()) for item in inner.split(",")]
    try:
        if any(char in value for char in (".", "e", "E")):
            return float(value)
        return int(value)
    except ValueError:
        return value.strip('"').strip("'")
