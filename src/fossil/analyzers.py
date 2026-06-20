from __future__ import annotations

import ast
import fnmatch
import re
from pathlib import Path

from fossil.models import Reference, StaticAnalysisResult
from fossil.repo import relpath

SOURCE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
}

DOC_EXTENSIONS = {".md", ".rst", ".txt", ".adoc"}
CONFIG_EXTENSIONS = {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}
SKIP_PARTS = {".git", ".fossil", "__pycache__", "node_modules", "dist", "build", ".venv", "venv"}


def language_for(path: Path) -> str:
    return SOURCE_EXTENSIONS.get(path.suffix.lower(), "unknown")


def iter_repo_files(repo_root: Path, exclude: list[str] | None = None) -> list[Path]:
    exclude = exclude or []
    files: list[Path] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root).as_posix()
        if any(part in SKIP_PARTS for part in path.relative_to(repo_root).parts):
            continue
        if any(fnmatch.fnmatch(rel, pattern) for pattern in exclude):
            continue
        files.append(path)
    return files


def exported_symbols(path: Path) -> set[str]:
    if path.suffix != ".py":
        return {path.stem}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return {path.stem}
    symbols = {path.stem}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                symbols.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    symbols.add(target.id)
    return symbols


def module_names(path: Path, repo_root: Path) -> set[str]:
    rel = path.relative_to(repo_root).with_suffix("")
    parts = list(rel.parts)
    names = {path.stem, ".".join(parts)}
    if parts[-1] == "__init__" and len(parts) > 1:
        names.add(".".join(parts[:-1]))
    return {name for name in names if name}


def analyze_file(
    path: Path, repo_root: Path, exclude: list[str] | None = None
) -> StaticAnalysisResult:
    language = language_for(path)
    symbols = exported_symbols(path)
    modules = module_names(path, repo_root)
    result = StaticAnalysisResult(language=language, unknown_language=language == "unknown")
    files = iter_repo_files(repo_root, exclude)
    target_rel = relpath(path, repo_root)

    for other in files:
        if other.resolve() == path.resolve():
            continue
        rel = relpath(other, repo_root)
        try:
            text = other.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if other.suffix == ".py":
            _scan_python(other, rel, text, modules, symbols, result)
        else:
            _scan_text(other, rel, text, modules, symbols, result, target_rel)
    _scan_dynamic_and_reflection(files, path, repo_root, modules, result)
    return result


def _add_ref(result: StaticAnalysisResult, path: str, line: int, kind: str, text: str) -> None:
    ref = Reference(path=path, line=line, kind=kind, text=text.strip()[:240])
    result.references.append(ref)
    if _is_test_path(path):
        result.test_file_references += 1
    elif kind == "import":
        result.import_references += 1
    elif kind == "call":
        result.call_sites += 1
    elif kind == "doc":
        result.documentation_references += 1
    elif kind == "config":
        result.config_file_references += 1


def _is_test_path(path: str) -> bool:
    lower = path.lower()
    return "/test" in lower or lower.startswith("test") or "_test." in lower


def _scan_python(
    path: Path,
    rel: str,
    text: str,
    modules: set[str],
    symbols: set[str],
    result: StaticAnalysisResult,
) -> None:
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        _scan_text(path, rel, text, modules, symbols, result, "")
        return
    imported_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in modules or any(alias.name.endswith("." + m) for m in modules):
                    imported_aliases.add(alias.asname or alias.name.split(".")[0])
                    _add_ref(result, rel, node.lineno, "import", lines[node.lineno - 1])
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module in modules or any(node.module.endswith("." + m) for m in modules):
                for alias in node.names:
                    imported_aliases.add(alias.asname or alias.name)
                _add_ref(result, rel, node.lineno, "import", lines[node.lineno - 1])
            elif any(alias.name in symbols for alias in node.names):
                _add_ref(result, rel, node.lineno, "import", lines[node.lineno - 1])
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name and (name in symbols or name.split(".")[0] in imported_aliases):
                _add_ref(result, rel, node.lineno, "call", lines[node.lineno - 1])
        elif isinstance(node, ast.Name) and node.id in symbols:
            _add_ref(
                result,
                rel,
                getattr(node, "lineno", 1),
                "call",
                lines[getattr(node, "lineno", 1) - 1],
            )


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def _scan_text(
    path: Path,
    rel: str,
    text: str,
    modules: set[str],
    symbols: set[str],
    result: StaticAnalysisResult,
    target_rel: str,
) -> None:
    needles = sorted(
        modules | symbols | ({target_rel} if target_rel else set()), key=len, reverse=True
    )
    if not needles:
        return
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in needles if n) + r")\b")
    kind = (
        "doc"
        if path.suffix.lower() in DOC_EXTENSIONS
        else "config"
        if path.suffix.lower() in CONFIG_EXTENSIONS
        else "call"
    )
    for idx, line in enumerate(text.splitlines(), 1):
        if pattern.search(line):
            _add_ref(result, rel, idx, kind, line)


def _scan_dynamic_and_reflection(
    files: list[Path],
    target: Path,
    repo_root: Path,
    modules: set[str],
    result: StaticAnalysisResult,
) -> None:
    dynamic_re = re.compile(r"(importlib\.import_module|__import__)\(([^)]*)\)")
    reflection_re = re.compile(r"\b(getattr|hasattr|setattr|vars)\(([^)]*)\)")
    module_re = re.compile("|".join(re.escape(m) for m in sorted(modules, key=len, reverse=True)))
    if not modules:
        return
    for path in files:
        if path.resolve() == target.resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = relpath(path, repo_root)
        for idx, line in enumerate(text.splitlines(), 1):
            if dynamic_re.search(line) and module_re.search(line):
                result.dynamic_references.append(Reference(rel, idx, "dynamic", line.strip()))
            if reflection_re.search(line) and module_re.search(line):
                result.reflection_patterns.append(Reference(rel, idx, "reflection", line.strip()))
