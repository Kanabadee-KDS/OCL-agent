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
    ollama_num_ctx: int = 32768
    ollama_keep_alive: str | None = "10m"
    ollama_think: bool = False

    gemini_api_key: str | None = None

    data_dir: Path = Path("./data")
    database_url: str | None = None

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    @field_validator("ollama_keep_alive", mode="before")
    @classmethod
    def _empty_keep_alive_is_none(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @model_validator(mode="after")
    def _protect_hris_model(self) -> Settings:
        # Rule 2: a keep_alive in any request overrides the HRIS keep_alive=-1 and
        # evicts gemma4:12b. Never send one when sharing that model.
        if self.ollama_model == HRIS_PINNED_MODEL and self.ollama_keep_alive is not None:
            raise ValueError(
                f"OLLAMA_KEEP_ALIVE must be empty when OLLAMA_MODEL={HRIS_PINNED_MODEL} "
                "(shared with HRIS); see docs/server-constraints.md rule 2"
            )
        if self.ollama_num_ctx <= 0:
            raise ValueError("OLLAMA_NUM_CTX must be positive and set explicitly")
        return self


def get_settings() -> Settings:
    return Settings()
