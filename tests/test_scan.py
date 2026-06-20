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
