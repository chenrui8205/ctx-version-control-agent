"""Typed configuration. All thresholds/weights live here — no magic numbers in logic (§14)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CTXVCS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://ctxvcs:ctxvcs@localhost:5433/ctxvcs"

    # §6 reconcile config
    tau_conf: float = 0.82  # embedding cosine-similarity threshold for candidate retrieval
    conf_min: float = 0.6  # below this, a non-collision `contradicts` is downgraded
    low_conf_contradicts_downgrade: str = "complementary"  # downgrade target (keep-both: no data loss)
    reconcile_max_candidates: int = 8  # cap LLM calls per incoming entry
    reconcile_model: str = "claude-sonnet-5"
    reconcile_max_tokens: int = 1024

    # embeddings (write path only — §13 forbids embedding-based consumption retrieval)
    embed_provider: str = "openai"  # openai | fake
    embed_model: str = "text-embedding-3-small"
    embed_dim: int = 1536

    # compiler
    template_version: str = "m0-v2"  # pages are functions of (master tree, template version)

    # evals (§12)
    eval_trials: int = 3  # majority vote over N classifier calls per pair
    eval_price_in_per_mtok: float = 3.0  # printed cost estimate for live runs
    eval_price_out_per_mtok: float = 15.0
    eval_est_tokens_per_call: int = 1500

    # auth
    token_bytes: int = 32


@lru_cache
def settings() -> Settings:
    return Settings()
