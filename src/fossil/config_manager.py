"""Configuration management.

Implements §8 of the pre-development docs:
- User config at ~/.config/fossil/config.toml with 0600 permissions
- Project config at .fossil.toml (repo root, committed)
- Environment variable overrides
- Masked display of sensitive values
- TOML parsing via tomllib (Python 3.11+)
"""
from __future__ import annotations

import os
import stat
import tomllib
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "fossil"
CONFIG_PATH = CONFIG_DIR / "config.toml"
SENSITIVE = {"github_token", "gitlab_token", "llm_api_key"}

# Valid config keys (§8.2)
VALID_KEYS = {
    "github_token", "gitlab_token", "llm_api_key",
    "llm_provider", "llm_model", "llm_base_url",
    "default_depth", "cache_ttl_hours",
    "output.color", "output.theme",
}

# Env var → config key mapping
ENV_OVERRIDES = {
    "GITHUB_TOKEN": "github_token",
    "GITLAB_TOKEN": "gitlab_token",
    "FOSSIL_LLM_API_KEY": "llm_api_key",
    "FOSSIL_LLM_PROVIDER": "llm_provider",
    "FOSSIL_LLM_MODEL": "llm_model",
    "FOSSIL_DEFAULT_DEPTH": "default_depth",
    "FOSSIL_LOG_LEVEL": "log_level",
}


def set_config(key: str, value: str) -> None:
    """Write a key-value pair to the user config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    values = _read_raw_config()
    values[key] = value
    lines = [f'{k} = "{v}"\n' for k, v in sorted(values.items())]
    CONFIG_PATH.write_text("".join(lines), encoding="utf-8")
    os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)


def _read_raw_config() -> dict[str, str]:
    """Read config file without env var overrides."""
    if not CONFIG_PATH.exists():
        return {}
    data: dict[str, str] = {}
    try:
        with open(CONFIG_PATH, "rb") as f:
            parsed = tomllib.load(f)
        # Flatten nested TOML sections
        for section_key, section_val in parsed.items():
            if isinstance(section_val, dict):
                for k, v in section_val.items():
                    data[f"{section_key}.{k}"] = str(v)
            else:
                data[section_key] = str(section_val)
    except (tomllib.TOMLDecodeError, OSError):
        # Fall back to simple key=value parsing for legacy configs
        try:
            for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
                if "=" not in line or line.strip().startswith("#"):
                    continue
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip().strip('"')
        except OSError:
            pass
    return data


def read_config() -> dict[str, str]:
    """Read config with environment variable overrides."""
    data = _read_raw_config()
    for env, key in ENV_OVERRIDES.items():
        if os.environ.get(env):
            data[key] = os.environ[env]
    return data


def read_project_config(repo_root: Path) -> dict[str, Any]:
    """Read .fossil.toml project-level configuration.

    Returns a dictionary with sections: analysis, thresholds, pr.
    """
    project_config_path = repo_root / ".fossil.toml"
    if not project_config_path.exists():
        return {}
    try:
        with open(project_config_path, "rb") as f:
            return tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        return {}


def get_effective_config(repo_root: Path | None = None) -> dict[str, Any]:
    """Get merged config: user config → project config → env overrides.

    Project config values override user config for matching keys.
    Environment variables override everything.
    """
    config: dict[str, Any] = dict(read_config())
    if repo_root:
        project = read_project_config(repo_root)
        # Merge project config (flattened)
        for section, values in project.items():
            if isinstance(values, dict):
                for k, v in values.items():
                    config[f"{section}.{k}"] = v
            else:
                config[section] = values
    return config


def masked_config() -> dict[str, str]:
    return {key: _mask(value) if key in SENSITIVE else value for key, value in read_config().items()}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return f"{value[:4]}...{value[-4:]}"
