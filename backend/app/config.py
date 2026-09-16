from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_PATH = _BACKEND_DIR / ".env"
_ENV_FILES = [str(_ENV_PATH), ".env"] if _ENV_PATH.exists() else [".env"]

class Settings(BaseSettings):
    neoalgo_env: str = "development"
    neoalgo_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
    database_url: str = "sqlite+aiosqlite:///./algo_trader.db"
    telegram_enabled: bool = True
    telegram_api_id: Optional[int] = None
    telegram_api_hash: Optional[str] = None
    telegram_session: Optional[str] = None
    telegram_session_path: str = "data/telethon_session"
    telegram_channel_id: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    broker_api_key: Optional[str] = None
    broker_api_secret: Optional[str] = None
    broker_access_token: Optional[str] = None
    
    # Kotak Neo API Configuration
    kotak_neo_consumer_key: Optional[str] = None
    kotak_neo_consumer_secret: Optional[str] = None # Added since it is in .env.example
    kotak_neo_mobile_number: Optional[str] = None
    kotak_neo_ucc: Optional[str] = None
    kotak_neo_mpin: Optional[str] = None
    kotak_neo_totp: Optional[str] = None
    kotak_neo_totp_secret: Optional[str] = None
    kotak_neo_environment: str = "prod"

    # Market Data Safety (Configurable stale tick threshold in seconds)
    market_data_stale_timeout_seconds: int = 60

    # Application Trading Mode ("PAPER" or "LIVE")
    trading_mode: str = "PAPER"

    # Single-User Auth (Phase 11C)
    neoalgo_admin_username: str = "admin"
    neoalgo_admin_password_hash: str = ""
    neoalgo_auth_secret: str = ""
    neoalgo_session_timeout_hours: int = 8

    model_config = SettingsConfigDict(env_file=_ENV_FILES, env_file_encoding="utf-8", extra="forbid")

settings = Settings()
