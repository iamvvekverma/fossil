"""Tests for the static analysis engine — Python analyzer and text fallback.

Covers §2.2 edge cases:
- Python import detection (regular imports, from-imports, aliased imports)
- Exported symbol detection (classes, functions, module-level names)
- Dynamic import detection (importlib, __import__)
- Reflection pattern detection (getattr, hasattr)
- Test file reference separation
- Documentation / config file reference detection
- Unknown language fallback via text search
"""
from __future__ import annotations

from pathlib import Path

from conftest import commit_all


def test_exported_symbols_python(tmp_path: Path):
    from fossil.analyzers import exported_symbols

    p = tmp_path / "module.py"
    p.write_text(
        "class MyClass:\n    pass\n\ndef public_func():\n    pass\n\n_private = 1\nPUBLIC_VAR = 2\n",
        encoding="utf-8",
    )
    symbols = exported_symbols(p)
    assert "MyClass" in symbols
    assert "public_func" in symbols
    assert "PUBLIC_VAR" in symbols
    assert "_private" not in symbols
    assert "module" in symbols  # stem


def test_exported_symbols_non_python(tmp_path: Path):
    from fossil.analyzers import exported_symbols

    p = tmp_path / "utils.js"
    p.write_text("export function doStuff() {}", encoding="utf-8")
    symbols = exported_symbols(p)
    assert symbols == {"utils"}  # only stem for non-python


def test_analyze_file_detects_python_imports(make_repo):
    from fossil.analyzers import analyze_file

    repo = make_repo()
    (repo / "legacy.py").write_text("class Legacy:\n    pass\n", encoding="utf-8")
    (repo / "main.py").write_text("from legacy import Legacy\nLegacy()\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = analyze_file(repo / "legacy.py", repo)
    assert result.import_references >= 1
    assert result.call_sites >= 1
    assert result.language == "python"


def test_analyze_file_no_references(make_repo):
    from fossil.analyzers import analyze_file

    repo = make_repo()
    (repo / "orphan.py").write_text("class Orphan:\n    pass\n", encoding="utf-8")
    (repo / "main.py").write_text("print('hello')\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = analyze_file(repo / "orphan.py", repo)
    assert result.import_references == 0
    assert result.call_sites == 0


def test_analyze_file_dynamic_import_detection(make_repo):
    from fossil.analyzers import analyze_file

    repo = make_repo()
    (repo / "legacy.py").write_text("class Legacy:\n    pass\n", encoding="utf-8")
    (repo / "loader.py").write_text(
        'import importlib\nmod = importlib.import_module("legacy")\n',
        encoding="utf-8",
    )
    commit_all(repo, "initial")

    result = analyze_file(repo / "legacy.py", repo)
    assert len(result.dynamic_references) >= 1


def test_analyze_file_reflection_detection(make_repo):
    from fossil.analyzers import analyze_file

    repo = make_repo()
    (repo / "legacy.py").write_text("class Legacy:\n    pass\n", encoding="utf-8")
    (repo / "caller.py").write_text(
        'import legacy\nobj = getattr(legacy, "Legacy")\n',
        encoding="utf-8",
    )
    commit_all(repo, "initial")

    result = analyze_file(repo / "legacy.py", repo)
    assert len(result.reflection_patterns) >= 1


def test_analyze_file_test_references_separated(make_repo):
    from fossil.analyzers import analyze_file

    repo = make_repo()
    (repo / "widget.py").write_text("class Widget:\n    pass\n", encoding="utf-8")
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_widget.py").write_text("from widget import Widget\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = analyze_file(repo / "widget.py", repo)
    assert result.test_file_references >= 1
    # Test refs should NOT count as main-code imports
    assert result.import_references == 0


def test_analyze_file_doc_reference(make_repo):
    from fossil.analyzers import analyze_file

    repo = make_repo()
    (repo / "billing.py").write_text("class BillingEngine:\n    pass\n", encoding="utf-8")
    (repo / "README.md").write_text("See billing.py for the billing engine.\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = analyze_file(repo / "billing.py", repo)
    assert result.documentation_references >= 1


def test_analyze_file_config_reference(make_repo):
    from fossil.analyzers import analyze_file

    repo = make_repo()
    (repo / "service.py").write_text("class Service:\n    pass\n", encoding="utf-8")
    (repo / "config.yaml").write_text("module: service\n", encoding="utf-8")
    commit_all(repo, "initial")

    result = analyze_file(repo / "service.py", repo)
    assert result.config_file_references >= 1


def test_language_detection():
    from fossil.analyzers import language_for

    assert language_for(Path("test.py")) == "python"
    assert language_for(Path("app.js")) == "javascript"
    assert language_for(Path("app.jsx")) == "javascript"
    assert language_for(Path("comp.ts")) == "typescript"
    assert language_for(Path("comp.tsx")) == "typescript"
    assert language_for(Path("Main.java")) == "java"
    assert language_for(Path("main.go")) == "go"
    assert language_for(Path("data.rb")) == "unknown"


def test_module_names():
    from fossil.analyzers import module_names

    repo = Path("/repo")
    names = module_names(Path("/repo/src/billing/processor.py"), repo)
    assert "processor" in names
    assert "src.billing.processor" in names


def test_iter_repo_files_skips_excluded(make_repo):
    from fossil.analyzers import iter_repo_files

    repo = make_repo()
    (repo / "main.py").write_text("x = 1\n", encoding="utf-8")
    nm = repo / "node_modules"
    nm.mkdir()
    (nm / "dep.js").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")

    files = iter_repo_files(repo)
    paths = {f.name for f in files}
    assert "main.py" in paths
    assert "dep.js" not in paths  # node_modules excluded


def test_iter_repo_files_glob_exclude(make_repo):
    from fossil.analyzers import iter_repo_files

    repo = make_repo()
    migrations = repo / "migrations"
    migrations.mkdir()
    (migrations / "001.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "main.py").write_text("x = 1\n", encoding="utf-8")
    commit_all(repo, "initial")

    files = iter_repo_files(repo, exclude=["migrations/*"])
    paths = {f.name for f in files}
    assert "main.py" in paths
    assert "001.py" not in paths
