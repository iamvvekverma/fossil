"""Tests for the SQLite cache store.

Covers §3.5:
- Analysis result CRUD
- Cache invalidation by git HEAD
- PR cache CRUD
- Cache stats
- Cache corruption recovery
- Size limit enforcement
"""

from __future__ import annotations

from pathlib import Path


def test_cache_put_and_get(tmp_path: Path):
    from fossil.cache import CacheStore

    store = CacheStore(tmp_path)
    file_path = tmp_path / "test.py"
    data = {"dead": True, "score": 91}
    store.put_analysis(file_path, "abc123", tmp_path, "0.1.0", data)

    result = store.get_analysis(file_path, "abc123", tmp_path)
    assert result is not None
    assert result["dead"] is True
    assert result["score"] == 91


def test_cache_miss_different_head(tmp_path: Path):
    from fossil.cache import CacheStore

    store = CacheStore(tmp_path)
    file_path = tmp_path / "test.py"
    store.put_analysis(file_path, "abc123", tmp_path, "0.1.0", {"dead": True})

    result = store.get_analysis(file_path, "different_head", tmp_path)
    assert result is None


def test_cache_clear(tmp_path: Path):
    from fossil.cache import CacheStore

    store = CacheStore(tmp_path)
    file_path = tmp_path / "test.py"
    store.put_analysis(file_path, "abc123", tmp_path, "0.1.0", {"dead": True})
    store.clear()

    result = store.get_analysis(file_path, "abc123", tmp_path)
    assert result is None


def test_cache_pr_crud(tmp_path: Path):
    from fossil.cache import CacheStore

    store = CacheStore(tmp_path)
    store.put_pr(
        "https://github.com/org/repo", 42, "Fix billing", "Full description", "2023-04-12T00:00:00Z"
    )

    result = store.get_pr("https://github.com/org/repo", 42)
    assert result is not None
    assert result["pr_title"] == "Fix billing"
    assert result["pr_body"] == "Full description"
    assert result["merged_at"] == "2023-04-12T00:00:00Z"


def test_cache_pr_miss(tmp_path: Path):
    from fossil.cache import CacheStore

    store = CacheStore(tmp_path)
    result = store.get_pr("https://github.com/org/repo", 999)
    assert result is None


def test_cache_stats(tmp_path: Path):
    from fossil.cache import CacheStore

    store = CacheStore(tmp_path)
    store.put_analysis(tmp_path / "a.py", "h1", tmp_path, "0.1.0", {"x": 1})
    store.put_analysis(tmp_path / "b.py", "h1", tmp_path, "0.1.0", {"x": 2})
    store.put_pr("url", 1, "title", "body", None)

    stats = store.stats()
    assert stats["analysis_count"] == 2
    assert stats["pr_count"] == 1
    assert stats["size_bytes"] > 0


def test_cache_oversized_result_skipped(tmp_path: Path):
    from fossil.cache import MAX_RESULT_BYTES, CacheStore

    store = CacheStore(tmp_path)
    # Create a payload larger than MAX_RESULT_BYTES
    huge = {"data": "x" * (MAX_RESULT_BYTES + 1000)}
    store.put_analysis(tmp_path / "big.py", "h1", tmp_path, "0.1.0", huge)

    result = store.get_analysis(tmp_path / "big.py", "h1", tmp_path)
    assert result is None  # Should not have been cached


def test_cache_corruption_recovery(tmp_path: Path):
    from fossil.cache import CacheStore

    store = CacheStore(tmp_path)
    # Create the cache file with garbage
    store.path.parent.mkdir(exist_ok=True)
    store.path.write_text("this is not valid sqlite", encoding="utf-8")

    # Should recover silently
    result = store.get_analysis(tmp_path / "test.py", "h1", tmp_path)
    assert result is None

    # After recovery, should work normally
    store.put_analysis(tmp_path / "test.py", "h1", tmp_path, "0.1.0", {"ok": True})
    result = store.get_analysis(tmp_path / "test.py", "h1", tmp_path)
    assert result is not None
    assert result["ok"] is True
