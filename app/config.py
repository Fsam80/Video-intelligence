from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env."""

    app_name: str = "Video Intelligence API"
    app_version: str = "0.2.0"
    environment: str = "development"

    # Storage
    data_dir: Path = Path("data")
    keep_media: bool = False  # delete downloaded/uploaded media after processing
    max_upload_mb: int = 500

    # Separate fetcher service (scraping/downloading lives outside this app)
    fetcher_url: str = "http://127.0.0.1:8001"
    fetcher_timeout_s: float = 600.0

    # Transcription (faster-whisper, runs locally on CPU by default)
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_language: str | None = None  # None = auto-detect

    # Analysis LLM: any OpenAI-compatible endpoint (Ollama, LM Studio, vLLM...)
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_api_key: str = "local"
    llm_timeout_s: float = 600.0
    llm_max_transcript_chars: int = 24000
    analysis_language: str = "français"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def db_path(self) -> Path:
        return self.data_dir / "video_intelligence.db"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"


settings = Settings()
