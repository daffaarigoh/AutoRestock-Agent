import os
from pathlib import Path

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    class _BaseSettings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore"
        )
except ImportError:
    from pydantic import BaseModel
    class _BaseSettings(BaseModel):
        pass


class Settings(_BaseSettings):

    # General
    APP_NAME: str = "AutoRestock-Agent"
    APP_ENV: str = "development"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True

    # Mock Mode
    MOCK_MODELS: bool = True

    # Model URLs
    MODEL_QWEN_URL: str = "http://localhost:8001/v1"
    MODEL_NEMOTRON_URL: str = "http://localhost:8002/v1"
    MODEL_OCR_LIGHTON_URL: str = "http://localhost:8003/v1"
    MODEL_QWEN_VISION_URL: str = "http://localhost:8004/v1"
    MODEL_API_KEY: str = "dummy-key"

    # File Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage"
    DOCUMENTS_DIR: Path = BASE_DIR / "storage" / "documents"
    ANNOTATED_DIR: Path = BASE_DIR / "storage" / "annotated"
    DATA_DIR: Path = BASE_DIR / "data"
    SAMPLES_DIR: Path = BASE_DIR / "data" / "samples"


settings = Settings()

# Ensure directories exist
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
settings.ANNOTATED_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
