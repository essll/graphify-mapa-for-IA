"""Persistent on-disk caching for computed graph structures (trigram index, IDF, etc.).

Provides TTL-based expiration, size limits, and automatic cleanup.
"""
from __future__ import annotations
import hashlib
import json
import os
import pickle
import time
from pathlib import Path
from typing import Any, Optional, TypeVar

from graphify.config import get_config

T = TypeVar("T")


class PersistentCache:
    """File-based persistent cache with TTL and size management."""

    def __init__(self, namespace: str, ttl_days: int, cache_dir: Optional[Path] = None):
        """
        Args:
            namespace: Logical namespace (e.g., "trigram_index", "idf")
            ttl_days: Time-to-live in days
            cache_dir: Override default cache directory
        """
        cfg = get_config()
        self.namespace = namespace
        self.ttl_seconds = ttl_days * 86400
        self.cache_dir = (cache_dir or cfg.cache.cache_dir) / namespace
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._max_size_bytes = cfg.cache.max_cache_size_mb * 1024 * 1024

    def _key_to_path(self, key: str) -> Path:
        """Convert a cache key to a safe filesystem path."""
        # Hash the key to avoid filesystem issues with long/special keys
        hashed = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self.cache_dir / f"{hashed}.cache"

    def _meta_path(self, key: str) -> Path:
        """Path for metadata (timestamp, size)."""
        return self._key_to_path(key).with_suffix(".meta")

    def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        """Retrieve a cached value if it exists and hasn't expired."""
        if not get_config().cache.enabled:
            return default

        path = self._key_to_path(key)
        meta_path = self._meta_path(key)

        if not path.exists() or not meta_path.exists():
            return default

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if time.time() - meta["timestamp"] > self.ttl_seconds:
                # Expired - clean up
                path.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
                return default

            with path.open("rb") as f:
                return pickle.load(f)
        except (json.JSONDecodeError, pickle.PickleError, OSError, KeyError):
            # Corrupted cache - remove and return default
            path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
            return default

    def set(self, key: str, value: Any) -> bool:
        """Store a value in the cache."""
        if not get_config().cache.enabled:
            return False

        path = self._key_to_path(key)
        meta_path = self._meta_path(key)

        try:
            # Write data
            with path.open("wb") as f:
                pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)

            # Write metadata
            size = path.stat().st_size
            meta = {"timestamp": time.time(), "size": size, "key": key}
            meta_path.write_text(json.dumps(meta), encoding="utf-8")

            # Enforce size limit (best-effort, async cleanup would be better)
            self._enforce_size_limit()

            return True
        except (OSError, pickle.PickleError):
            path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
            return False

    def delete(self, key: str) -> bool:
        """Remove a specific key from cache."""
        path = self._key_to_path(key)
        meta_path = self._meta_path(key)
        removed = False
        if path.exists():
            path.unlink()
            removed = True
        if meta_path.exists():
            meta_path.unlink()
            removed = True
        return removed

    def clear(self) -> int:
        """Clear all entries in this namespace. Returns count of removed files."""
        count = 0
        for path in self.cache_dir.glob("*.cache"):
            path.unlink(missing_ok=True)
            count += 1
        for path in self.cache_dir.glob("*.meta"):
            path.unlink(missing_ok=True)
        return count

    def _enforce_size_limit(self) -> None:
        """Remove oldest entries if total size exceeds limit."""
        if self._max_size_bytes <= 0:
            return

        entries = []
        total_size = 0
        for meta_path in self.cache_dir.glob("*.meta"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                entries.append((meta["timestamp"], meta["size"], meta_path))
                total_size += meta["size"]
            except (json.JSONDecodeError, KeyError, OSError):
                # Corrupted meta - remove both files
                cache_path = meta_path.with_suffix(".cache")
                cache_path.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)

        if total_size <= self._max_size_bytes:
            return

        # Sort by timestamp (oldest first) and remove until under limit
        entries.sort(key=lambda x: x[0])
        for _, size, meta_path in entries:
            if total_size <= self._max_size_bytes:
                break
            cache_path = meta_path.with_suffix(".cache")
            cache_path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
            total_size -= size

    def stats(self) -> dict:
        """Return cache statistics."""
        count = 0
        total_size = 0
        oldest = None
        newest = None
        for meta_path in self.cache_dir.glob("*.meta"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                count += 1
                total_size += meta["size"]
                ts = meta["timestamp"]
                if oldest is None or ts < oldest:
                    oldest = ts
                if newest is None or ts > newest:
                    newest = ts
            except (json.JSONDecodeError, KeyError, OSError):
                pass
        return {
            "namespace": self.namespace,
            "entries": count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "oldest_entry": oldest,
            "newest_entry": newest,
        }


# Pre-configured cache instances for common use cases
_trigram_cache: Optional[PersistentCache] = None
_idf_cache: Optional[PersistentCache] = None


def get_trigram_cache() -> PersistentCache:
    """Get the global trigram index cache."""
    global _trigram_cache
    if _trigram_cache is None:
        cfg = get_config()
        _trigram_cache = PersistentCache(
            "trigram_index",
            cfg.cache.trigram_index_ttl_days,
        )
    return _trigram_cache


def get_idf_cache() -> PersistentCache:
    """Get the global IDF cache."""
    global _idf_cache
    if _idf_cache is None:
        cfg = get_config()
        _idf_cache = PersistentCache(
            "idf",
            cfg.cache.idf_cache_ttl_days,
        )
    return _idf_cache


def clear_all_caches() -> dict:
    """Clear all persistent caches. Returns stats of what was cleared."""
    results = {}
    for name, cache_fn in [("trigram_index", get_trigram_cache), ("idf", get_idf_cache)]:
        cache = cache_fn()
        stats = cache.stats()
        cache.clear()
        results[name] = stats
    return results


def get_cache_stats() -> dict:
    """Get statistics for all caches."""
    return {
        "trigram_index": get_trigram_cache().stats(),
        "idf": get_idf_cache().stats(),
    }