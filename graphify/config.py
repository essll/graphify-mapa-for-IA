"""Centralized configuration for graphify using pydantic-settings.

All magic numbers, thresholds, and tunable parameters are defined here
with sensible defaults. Can be overridden via environment variables
(prefixed with GRAPHIFY_) or a .env file.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DeduplicationConfig(BaseSettings):
    """Entity deduplication thresholds and behavior."""
    model_config = SettingsConfigDict(env_prefix="GRAPHIFY_DEDUP_", extra="ignore")

    entropy_threshold: float = Field(
        default=2.5,
        description="Minimum Shannon entropy (bits/char) for a label to enter fuzzy dedup"
    )
    lsh_threshold: float = Field(
        default=0.7,
        description="MinHash LSH Jaccard threshold for candidate blocking"
    )
    merge_threshold: float = Field(
        default=92.0,
        description="Jaro-Winkler score (0-100) required to merge two entities"
    )
    community_boost: float = Field(
        default=5.0,
        description="Score bonus when both nodes share a community"
    )
    num_perm: int = Field(
        default=128,
        description="Number of MinHash permutations"
    )
    llm_low: float = Field(
        default=75.0,
        description="Lower bound for LLM tiebreaker zone"
    )
    llm_high: float = Field(
        default=92.0,
        description="Upper bound for LLM tiebreaker zone (merge_threshold)"
    )


class ClusteringConfig(BaseSettings):
    """Community detection (Leiden/Louvain) parameters."""
    model_config = SettingsConfigDict(env_prefix="GRAPHIFY_CLUSTER_", extra="ignore")

    resolution: float = Field(
        default=1.0,
        description="Resolution parameter: >1 = more/smaller communities, <1 = fewer/larger"
    )
    max_community_fraction: float = Field(
        default=0.25,
        description="Communities larger than this fraction of graph get split"
    )
    min_split_size: int = Field(
        default=10,
        description="Minimum community size to attempt splitting"
    )
    cohesion_split_threshold: float = Field(
        default=0.05,
        description="Re-split communities with cohesion below this"
    )
    cohesion_split_min_size: int = Field(
        default=50,
        description="Minimum size for cohesion-based re-split"
    )
    exclude_hubs_percentile: Optional[float] = Field(
        default=None,
        description="Exclude nodes above this degree percentile from partitioning (0-100)"
    )


class QueryConfig(BaseSettings):
    """Query engine scoring and traversal parameters."""
    model_config = SettingsConfigDict(env_prefix="GRAPHIFY_QUERY_", extra="ignore")

    exact_match_bonus: float = Field(
        default=1000.0,
        description="Score bonus for full-query exact label match"
    )
    prefix_match_bonus: float = Field(
        default=100.0,
        description="Score bonus for full-query prefix label match"
    )
    substring_match_bonus: float = Field(
        default=1.0,
        description="Score bonus for substring match"
    )
    source_match_bonus: float = Field(
        default=0.5,
        description="Score bonus for source_file token match"
    )
    default_token_budget: int = Field(
        default=2000,
        description="Default output token budget for query results"
    )
    default_depth: int = Field(
        default=3,
        description="Default BFS/DFS traversal depth"
    )
    max_depth: int = Field(
        default=6,
        description="Maximum allowed traversal depth"
    )
    hub_threshold_percentile: float = Field(
        default=0.99,
        description="Degree percentile above which nodes are treated as hubs (not expanded)"
    )
    hub_threshold_floor: int = Field(
        default=50,
        description="Minimum hub threshold degree"
    )
    gap_ratio: float = Field(
        default=0.2,
        description="Score gap ratio for seed selection (stop when score < top * gap_ratio)"
    )
    max_seeds: int = Field(
        default=3,
        description="Maximum seed nodes for BFS/DFS"
    )


class GraphConfig(BaseSettings):
    """Graph build and storage limits."""
    model_config = SettingsConfigDict(env_prefix="GRAPHIFY_GRAPH_", extra="ignore")

    max_graph_bytes: int = Field(
        default=512 * 1024 * 1024,  # 512 MiB
        description="Maximum graph.json size before refusing to load"
    )
    max_output_tokens: int = Field(
        default=16384,
        description="LLM output token cap for semantic extraction"
    )
    api_timeout: int = Field(
        default=600,
        description="HTTP timeout for LLM API calls (seconds)"
    )
    max_retries: int = Field(
        default=6,
        description="Max retries for rate-limited (429) requests"
    )
    max_workers: int = Field(
        default=0,
        description="AST parallelism thread count (0 = auto)"
    )


class CacheConfig(BaseSettings):
    """Persistent caching for trigram index, IDF, and other computed structures."""
    model_config = SettingsConfigDict(env_prefix="GRAPHIFY_CACHE_", extra="ignore")

    enabled: bool = Field(
        default=True,
        description="Enable persistent on-disk caching"
    )
    cache_dir: Path = Field(
        default=Path(".graphify_cache"),
        description="Directory for persistent cache files"
    )
    trigram_index_ttl_days: int = Field(
        default=7,
        description="TTL for trigram index cache (days)"
    )
    idf_cache_ttl_days: int = Field(
        default=7,
        description="TTL for IDF cache (days)"
    )
    max_cache_size_mb: int = Field(
        default=500,
        description="Maximum total cache size in MB"
    )


class SecurityConfig(BaseSettings):
    """Security and validation limits."""
    model_config = SettingsConfigDict(env_prefix="GRAPHIFY_SECURITY_", extra="ignore")

    max_node_id_length: int = Field(
        default=256,
        description="Maximum allowed node ID length"
    )
    max_label_length: int = Field(
        default=256,
        description="Maximum allowed label length"
    )
    max_source_file_length: int = Field(
        default=4096,
        description="Maximum allowed source_file path length"
    )
    allowed_url_schemes: tuple[str, ...] = Field(
        default=("http", "https"),
        description="Allowed URL schemes for ingestion"
    )


class Config(BaseSettings):
    """Root configuration aggregating all sub-configs."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    dedup: DeduplicationConfig = Field(default_factory=DeduplicationConfig)
    cluster: ClusteringConfig = Field(default_factory=ClusteringConfig)
    query: QueryConfig = Field(default_factory=QueryConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)

    # Global settings
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    no_backup: bool = Field(
        default=False,
        description="Disable automatic backup of graph artifacts before overwrite"
    )


# Global singleton instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance (lazy initialization)."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config() -> None:
    """Reset the global configuration (mainly for testing)."""
    global _config
    _config = None