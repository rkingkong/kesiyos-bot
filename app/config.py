"""
Kesiyos Bot — Application Configuration

All settings loaded from environment variables / .env file.
Uses Pydantic Settings for validation and type coercion.
"""

from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Application ---
    app_env: str = "production"
    app_port: int = 8444
    app_log_level: str = "INFO"
    app_log_dir: str = "/var/log/kesiyos-bot"

    # --- Database ---
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "kesiyos_bot"
    db_user: str = "kesiyos_bot"
    db_password: str

    @property
    def database_url(self) -> str:
        """Async PostgreSQL connection string for SQLAlchemy."""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync PostgreSQL connection string for Alembic migrations."""
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # --- Meta Platform (Facebook + Instagram) ---
    meta_app_secret: str = ""
    meta_verify_token: str = ""
    meta_page_access_token: str = ""
    meta_page_id: str = ""

    # --- WhatsApp Cloud API (staff escalation) ---
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    escalation_staff_phones: List[str] = []

    @field_validator("escalation_staff_phones", mode="before")
    @classmethod
    def parse_phone_list(cls, v):
        """Parse JSON string list from .env into Python list."""
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # Support comma-separated fallback
                return [p.strip() for p in v.split(",") if p.strip()]
        return v

    # --- Claude API ---
    anthropic_api_key: str = ""

    # --- Odoo XML-RPC (Phase 2 — not required at launch) ---
    odoo_url: str = "http://localhost:8069"
    odoo_db: str = ""
    odoo_user: str = ""
    odoo_password: str = ""

    # --- Derived paths ---
    @property
    def knowledge_base_path(self) -> Path:
        """Path to the knowledge base markdown file."""
        return Path(__file__).parent / "knowledge_base.md"


# Singleton instance — import this everywhere
settings = Settings()
