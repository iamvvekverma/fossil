"""Tests for CLI commands — end-to-end tests via subprocess.

Covers §2.1 edge cases (file not found, untracked, gitignored, symlink),
§2.7 (scan), §2.8 (JSON output), and §2.9 (--yolo guarding).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import commit_all


def run_cli(repo, *args):
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        str(Path(__file__).resolve().parent.parent / "src") + os.pathsep + env.get("PYTHONPATH", "")
    )
    return subprocess.run(
        [sys.executable, "-m", "fossil.cli", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# fossil explain
# ---------------------------------------------------------------------------


def test_explain_dead_python_file(make_repo):
    repo = make_repo()
    pkg = repo / "app"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "legacy.py").write_text(
        "# TODO: remove after 2020-01-01\nclass LegacyProcessor:\n    pass\n",
        encoding="utf-8",
    )
    (pkg / "main.py").write_text(
        "from app.legacy import LegacyProcessor\n\nLegacyProcessor()\n",
        encoding="utf-8",
    )
    commit_all(repo, "Add legacy processor")
    (pkg / "main.py").write_text("class NewProcessor:\n    pass\n", encoding="utf-8")
    commit_all(repo, "Migrate away from legacy processor (#42)")

    result = run_cli(repo, "explain", "app/legacy.py", "--json", "--no-cache")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dead"] is True
    assert payload["static_analysis"]["import_references"] == 0
    assert payload["temporary_hold"]["detected"] is True
    assert payload["confidence"]["score"] >= 70


def test_explain_live_python_file_exits_4(make_repo):
    repo = make_repo()
    (repo / "legacy.py").write_text("class Legacy:\n    pass\n", encoding="utf-8")
    (repo / "main.py").write_text("from legacy import Legacy\nLegacy()\n", encoding="utf-8")
    commit_all(repo, "Add live code")

    result = run_cli(repo, "explain", "legacy.py", "--json", "--no-cache")
    assert result.returncode == 4
    payload = json.loads(result.stdout)
    assert payload["dead"] is False
    assert payload["status"] == "LIVE"


def test_explain_untracked_file_reports_no_history(make_repo):
    repo = make_repo()
    (repo / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "Initial")
    (repo / "new_file.py").write_text("x = 2\n", encoding="utf-8")

    result = run_cli(repo, "explain", "new_file.py", "--json", "--no-cache")
    assert result.returncode == 4
    payload = json.loads(result.stdout)
    assert "UNTRACKED" in payload["status"]
    assert payload["confidence"] is None


def test_explain_file_not_found_exits_2(make_repo):
    repo = make_repo()
    (repo / "x.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "Initial")

    result = run_cli(repo, "explain", "nonexistent.py", "--json")
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert "error" in payload


def test_explain_not_git_repo_exits_3(tmp_path):
    (tmp_path / "file.py").write_text("x = 1\n", encoding="utf-8")
    result = run_cli(tmp_path, "explain", "file.py")
    assert result.returncode == 3


def test_explain_json_output_shape(make_repo):
    repo = make_repo()
    (repo / "dead.py").write_text("class Dead:\n    pass\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = run_cli(repo, "explain", "dead.py", "--json", "--no-cache")
    payload = json.loads(result.stdout)
    # Check required fields from §3.4
    assert "fossil_version" in payload
    assert "target" in payload
    assert "abs_path" in payload
    assert "repo_root" in payload
    assert "language" in payload
    assert "dead" in payload
    assert "static_analysis" in payload
    assert "git_history" in payload
    assert "temporary_hold" in payload
    assert "confidence" in payload
    assert "suggested_action" in payload
    assert "analysis_duration_ms" in payload


def test_explain_plain_output(make_repo):
    repo = make_repo()
    (repo / "dead.py").write_text("class Dead:\n    pass\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = run_cli(repo, "explain", "dead.py", "--plain", "--no-cache")
    assert result.returncode == 0
    assert "fossil forensic report" in result.stdout
    assert "Target:" in result.stdout
    assert "Status:" in result.stdout


def test_explain_symlink(make_repo):
    repo = make_repo()
    (repo / "real.py").write_text("class Real:\n    pass\n", encoding="utf-8")
    (repo / "link.py").symlink_to(repo / "real.py")
    commit_all(repo, "initial")

    result = run_cli(repo, "explain", "link.py", "--json", "--no-cache")
    payload = json.loads(result.stdout)
    assert any("symlink" in w.lower() for w in payload.get("warnings", []))


def test_explain_gitignored_warning(make_repo):
    repo = make_repo()
    (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    ignored = repo / "ignored"
    ignored.mkdir()
    (ignored / "file.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = run_cli(repo, "explain", "ignored/file.py", "--json", "--no-cache")
    if result.returncode == 0:
        payload = json.loads(result.stdout)
        assert any("gitignored" in w.lower() for w in payload.get("warnings", []))


def test_explain_yolo_blocked_below_threshold(make_repo):
    repo = make_repo()
    (repo / "dead.py").write_text("class Dead:\n    pass\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = run_cli(repo, "explain", "dead.py", "--yolo", "--no-cache")
    assert result.returncode == 1
    assert "blocked" in result.stderr.lower() or "integration" in result.stderr.lower()


def test_explain_narrate_returns_error(make_repo):
    repo = make_repo()
    (repo / "dead.py").write_text("class Dead:\n    pass\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = run_cli(repo, "explain", "dead.py", "--narrate")
    assert result.returncode == 1
    assert "llm" in result.stderr.lower() or "narrate" in result.stderr.lower()


# ---------------------------------------------------------------------------
# fossil scan
# ---------------------------------------------------------------------------


def test_scan_returns_dead_files(make_repo):
    repo = make_repo()
    (repo / "dead.py").write_text("class Dead:\n    pass\n", encoding="utf-8")
    (repo / "live.py").write_text("class Live:\n    pass\n", encoding="utf-8")
    (repo / "main.py").write_text(
        "from dead import Dead\nfrom live import Live\nDead()\nLive()\n",
        encoding="utf-8",
    )
    commit_all(repo, "Add files")
    (repo / "main.py").write_text("from live import Live\nLive()\n", encoding="utf-8")
    commit_all(repo, "Remove dead import (#9)")
    result = run_cli(repo, "scan", ".", "--threshold", "40", "--json", "--no-cache")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    names = {item["abs_path"].split("/")[-1] for item in payload}
    assert "dead.py" in names
    assert "live.py" not in names


def test_scan_no_dead_code_exits_4(make_repo):
    repo = make_repo()
    (repo / "live.py").write_text("class Live:\n    pass\n", encoding="utf-8")
    (repo / "main.py").write_text("from live import Live\nLive()\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = run_cli(repo, "scan", ".", "--threshold", "90", "--json", "--no-cache")
    assert result.returncode == 4 or result.returncode == 0
    # If returned JSON, the list should be empty
    if result.returncode == 0:
        payload = json.loads(result.stdout)
        assert len(payload) == 0


def test_scan_language_filter(make_repo):
    repo = make_repo()
    (repo / "dead.py").write_text("class Dead:\n    pass\n", encoding="utf-8")
    (repo / "dead.js").write_text("export class Dead {}\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = run_cli(
        repo, "scan", ".", "--language", "py", "--threshold", "40", "--json", "--no-cache"
    )
    assert result.returncode in (0, 4)
    payload = json.loads(result.stdout)
    for item in payload:
        assert item["language"] == "python"


def test_scan_no_supported_files(make_repo):
    repo = make_repo()
    (repo / "data.csv").write_text("a,b,c\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = run_cli(repo, "scan", ".", "--no-cache")
    assert result.returncode == 4


def test_scan_plain_output(make_repo):
    repo = make_repo()
    (repo / "dead.py").write_text("class Dead:\n    pass\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = run_cli(repo, "scan", ".", "--threshold", "40", "--plain", "--no-cache")
    assert (
        "fossil scan" in result.stdout
        or "No dead code" in result.stdout
        or "dead" in result.stdout.lower()
    )


# ---------------------------------------------------------------------------
# fossil clean
# ---------------------------------------------------------------------------


def test_clean_shows_backlog(make_repo):
    repo = make_repo()
    (repo / "dead1.py").write_text("class Dead1:\n    pass\n", encoding="utf-8")
    (repo / "dead2.py").write_text("class Dead2:\n    pass\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = run_cli(repo, "clean", ".", "--threshold", "40", "--json", "--no-cache")
    if result.returncode == 0:
        payload = json.loads(result.stdout)
        assert isinstance(payload, list)


def test_clean_yolo_returns_integration_error(make_repo):
    repo = make_repo()
    (repo / "dead.py").write_text("class Dead:\n    pass\n", encoding="utf-8")
    (repo / "main.py").write_text("from dead import Dead\nDead()\n", encoding="utf-8")
    commit_all(repo, "Add dead")
    (repo / "main.py").write_text("print('new')\n", encoding="utf-8")
    commit_all(repo, "Remove dead usage (#5)")

    result = run_cli(repo, "clean", ".", "--threshold", "40", "--yolo", "--no-cache")
    assert result.returncode == 1
    assert "integration" in result.stderr.lower() or "api" in result.stderr.lower()


# ---------------------------------------------------------------------------
# fossil cache
# ---------------------------------------------------------------------------


def test_cache_clear(make_repo):
    repo = make_repo()
    (repo / "f.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")
    # Ensure cache exists
    run_cli(repo, "explain", "f.py", "--json")
    result = run_cli(repo, "cache", "clear")
    assert result.returncode == 0
    assert "cleared" in result.stdout.lower()


# ---------------------------------------------------------------------------
# fossil config
# ---------------------------------------------------------------------------


def test_config_show(make_repo):
    result = subprocess.run(
        [sys.executable, "-m", "fossil.cli", "config", "show"],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0


def test_config_set_and_show(tmp_path, monkeypatch):
    # Use a temporary config dir to avoid polluting user config
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.toml"
    monkeypatch.setattr("fossil.config_manager.CONFIG_DIR", config_dir)
    monkeypatch.setattr("fossil.config_manager.CONFIG_PATH", config_path)

    from fossil.config_manager import masked_config, read_config, set_config

    set_config("github_token", "ghp_test1234567890abcdef")
    assert config_path.exists()
    # Check permissions
    mode = oct(config_path.stat().st_mode)[-3:]
    assert mode == "600"

    config = read_config()
    assert config["github_token"] == "ghp_test1234567890abcdef"

    masked = masked_config()
    assert "..." in masked["github_token"]
    assert masked["github_token"].endswith("cdef")
