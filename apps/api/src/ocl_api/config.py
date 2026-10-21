"""Runtime settings loaded from environment / .env.

Guards here encode the shared-server rules in docs/server-constraints.md so a
misconfiguration fails at startup instead of evicting the HRIS model at runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

HRIS_PINNED_MODEL = "gemma4:12b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: Literal["ollama", "gemini"] = "ollama"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:26b"
    ollama_num_ctx: int | None = 32768
    ollama_keep_alive: str | None = "10m"
    ollama_think: bool = False

    gemini_api_key: str | None = None

    data_dir: Path = Path("./data")
    database_url: str | None = None

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # dev: the API runs jobs itself in a background thread; compose: a separate `ocl worker`
    inline_worker: bool = True
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @field_validator("ollama_keep_alive", "ollama_num_ctx", mode="before")
    @classmethod
    def _empty_is_none(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @model_validator(mode="after")
    def _protect_hris_model(self) -> Settings:
        # Rule 2 (verified 20 Oct 2569 the hard way): every request resets the model's
        # expiry. Omitting keep_alive applies Ollama's 5-minute default and un-pins the
        # HRIS model; a different num_ctx forces a full reload. When sharing gemma4:12b,
        # keep_alive must be exactly "-1" and num_ctx must not be sent at all.
        if self.ollama_model == HRIS_PINNED_MODEL:
            if self.ollama_keep_alive != "-1":
                raise ValueError(
                    f"OLLAMA_KEEP_ALIVE must be -1 when OLLAMA_MODEL={HRIS_PINNED_MODEL} "
                    "(shared with HRIS); see docs/server-constraints.md rule 2"
                )
            if self.ollama_num_ctx is not None:
                raise ValueError(
                    f"OLLAMA_NUM_CTX must be empty when OLLAMA_MODEL={HRIS_PINNED_MODEL} "
                    "(changing it reloads the HRIS model); see rule 2"
                )
        else:
            if self.ollama_num_ctx is None or self.ollama_num_ctx <= 0:
                raise ValueError("OLLAMA_NUM_CTX must be a positive integer for OCL models")
            if self.ollama_keep_alive is None:
                raise ValueError("OLLAMA_KEEP_ALIVE must be set (e.g. 10m) for OCL models")
        return self


def get_settings() -> Settings:
    return Settings()
