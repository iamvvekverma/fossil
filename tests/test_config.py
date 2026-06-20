"""Tests for project config (.fossil.toml) reading.

Covers §8.3 of the pre-development docs.
"""
from __future__ import annotations

from pathlib import Path


def test_read_project_config(tmp_path: Path):
    from fossil.config_manager import read_project_config

    config_file = tmp_path / ".fossil.toml"
    config_file.write_text(
        '[analysis]\nlanguages = ["py", "js"]\nexclude_patterns = ["**/migrations/**"]\n\n'
        '[thresholds]\nminimum_confidence = 75\nyolo_minimum_confidence = 90\n\n'
        '[pr]\nbase_branch = "main"\npr_labels = ["cleanup"]\n',
        encoding="utf-8",
    )

    config = read_project_config(tmp_path)
    assert config["analysis"]["languages"] == ["py", "js"]
    assert config["analysis"]["exclude_patterns"] == ["**/migrations/**"]
    assert config["thresholds"]["minimum_confidence"] == 75
    assert config["pr"]["base_branch"] == "main"


def test_read_project_config_missing(tmp_path: Path):
    from fossil.config_manager import read_project_config

    config = read_project_config(tmp_path)
    assert config == {}


def test_read_project_config_invalid_toml(tmp_path: Path):
    from fossil.config_manager import read_project_config

    config_file = tmp_path / ".fossil.toml"
    config_file.write_text("this is not valid toml [[[", encoding="utf-8")

    config = read_project_config(tmp_path)
    assert config == {}


def test_env_overrides():
    import os

    from fossil.config_manager import read_config

    os.environ["GITHUB_TOKEN"] = "ghp_test_env_token"
    try:
        config = read_config()
        assert config.get("github_token") == "ghp_test_env_token"
    finally:
        del os.environ["GITHUB_TOKEN"]


def test_mask_short_value():
    from fossil.config_manager import _mask

    assert _mask("abc") == "****"
    assert _mask("") == ""


def test_mask_long_value():
    from fossil.config_manager import _mask

    result = _mask("ghp_1234567890abcdef")
    assert result.startswith("ghp_")
    assert result.endswith("cdef")
    assert "..." in result
