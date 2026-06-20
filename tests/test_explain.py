from __future__ import annotations

import json
import subprocess
import sys

from conftest import commit_all


def run_cli(repo, *args):
    return subprocess.run(
        [sys.executable, "-m", "fossil.cli", *args],
        cwd=repo,
        text=True,
        capture_output=True,
    )


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

