"""
AutoRestock-V2 Configuration Module
Centralized settings management using Pydantic Settings.
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
import os

# Base directory for the V2 project
BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    APP_NAME: str = "AutoRestock-V2"
    APP_ENV: str = "development"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8050
    DEBUG: bool = True
    
    # Mock Mode: Set to true to allow self-contained execution without external LLM/OCR services
    MOCK_MODELS: bool = True
    
    # Model API Endpoints & Keys
    LLM_KEY: str = "sk-c1PP5Ngd9Dh7q2ZjiwZAIg"
    LLM_URL: str = "http://10.7.1.21/v1"
    DEFAULT_LLM_MODEL: str = "qwen-35b"
    VISION_LLM_MODEL: str = "qwen-35b-vision"
    OCR_MODEL: str = "ocr-lighton"
    NEMOTRON_MODEL: str = "nemotron-35"
    
    # Optional dedicated microservices
    MODEL_QWEN_URL: str = "http://10.7.1.21/v1"
    MODEL_NEMOTRON_URL: str = "http://10.7.1.21/v1"
    MODEL_OCR_LIGHTON_URL: str = "http://10.7.1.21/v1"
    MODEL_QWEN_VISION_URL: str = "http://10.7.1.21/v1"
    
    # Storage and Data Directories
    STORAGE_DIR: Path = BASE_DIR / "storage"
    DATA_DIR: Path = BASE_DIR / "data"
    DB_PATH: Path = BASE_DIR / "storage" / "inventory.db"
    
    # Business Logic & Thresholds
    AUTO_APPROVE_THRESHOLD_IDR: float = 5_000_000.0  # Under 5M IDR auto-approved
    DEFAULT_SAFETY_STOCK_BUFFER: float = 1.25       # 25% safety buffer
    DEFAULT_LEAD_TIME_DAYS: int = 3
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    
    # n8n Automation Webhooks
    N8N_ENABLED: bool = True
    N8N_WEBHOOK_NOTIFY_URL: str = "http://localhost:5678/webhook/notify"
    N8N_WEBHOOK_PO_DISPATCH_URL: str = "http://localhost:5678/webhook/po-dispatch"
    N8N_WEBHOOK_SYNC_URL: str = "http://localhost:5678/webhook/sync-sheets"
    
    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()

# Ensure directories exist
def ensure_directories():
    directories = [
        settings.STORAGE_DIR,
        settings.STORAGE_DIR / "documents",
        settings.STORAGE_DIR / "annotated",
        settings.STORAGE_DIR / "pending",
        settings.STORAGE_DIR / "approved",
        settings.STORAGE_DIR / "rejected",
        settings.STORAGE_DIR / "uploads",
        settings.DATA_DIR,
        settings.DATA_DIR / "samples",
    ]
    for d in directories:
        d.mkdir(parents=True, exist_ok=True)

ensure_directories()
