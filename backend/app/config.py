from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    LLM API keys are read exclusively from env vars and must never
    appear in database records, API responses, or frontend code
    (Requirement 11.2).
    """

    # Database
    database_url: str = Field(
        default="sqlite:///./veridoc.db",
        description="SQLAlchemy database connection URL",
    )

    # Redis / Celery
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL used as Celery broker",
    )

    # LLM API keys — env-only, never persisted (Req 11.2)
    openai_api_key: str = Field(default="", description="OpenAI API key")
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    google_api_key: str = Field(default="", description="Google Generative AI API key")

    # AWS Bedrock
    aws_access_key_id: str = Field(default="", description="AWS access key for Bedrock")
    aws_secret_access_key: str = Field(default="", description="AWS secret key for Bedrock")
    aws_region: str = Field(default="us-east-1", description="AWS region for Bedrock")
    bedrock_model_id: str = Field(
        default="anthropic.claude-3-5-sonnet-20241022-v2:0",
        description="Bedrock model ID",
    )

    # Upload / execution limits
    max_file_size: int = Field(
        default=1_048_576,
        description="Maximum upload file size in bytes (default 1 MB)",
    )
    test_timeout: int = Field(
        default=30,
        description="Timeout in seconds for individual test execution",
    )

    # CORS
    frontend_origin: str = Field(
        default="http://localhost:5173",
        description="Allowed frontend origin for CORS",
    )

    model_config = {"env_prefix": "VERIDOC_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
