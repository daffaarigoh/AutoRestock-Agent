import os
from pathlib import Path
from typing import Optional, Any

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

    # Alternative standard env keys
    LLM_KEY: Optional[str] = None
    LLM_URL: Optional[str] = None

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
    PENDING_DIR: Path = BASE_DIR / "storage" / "pending"
    APPROVED_DIR: Path = BASE_DIR / "storage" / "approved"
    REJECTED_DIR: Path = BASE_DIR / "storage" / "rejected"
    ANNOTATED_DIR: Path = BASE_DIR / "storage" / "annotated"
    DATA_DIR: Path = BASE_DIR / "data"
    SAMPLES_DIR: Path = BASE_DIR / "data" / "samples"

    def model_post_init(self, __context: Any) -> None:
        # If LLM_KEY is provided, sync with MODEL_API_KEY
        if self.LLM_KEY and (self.MODEL_API_KEY == "dummy-key" or not self.MODEL_API_KEY):
            self.MODEL_API_KEY = self.LLM_KEY.strip().strip('"').strip("'")
        
        # If LLM_URL is provided, sync with model base URLs
        if self.LLM_URL:
            base_url = self.LLM_URL.strip().strip('"').strip("'").rstrip("/")
            if "/v1" not in base_url:
                base_url = f"{base_url}/v1"
            if self.MODEL_QWEN_URL == "http://localhost:8001/v1":
                self.MODEL_QWEN_URL = base_url
            if self.MODEL_NEMOTRON_URL == "http://localhost:8002/v1":
                self.MODEL_NEMOTRON_URL = base_url


settings = Settings()

# Ensure directories exist
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
settings.PENDING_DIR.mkdir(parents=True, exist_ok=True)
settings.APPROVED_DIR.mkdir(parents=True, exist_ok=True)
settings.REJECTED_DIR.mkdir(parents=True, exist_ok=True)
settings.ANNOTATED_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

