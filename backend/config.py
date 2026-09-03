from pydantic_settings import BaseSettings,  SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_hostname: str
    database_port: int
    database_name: str
    database_username: str
    database_password: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int

    smtp_host: str
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "AMAlost <noreply@ama.edu.ph>"
    smtp_tls: bool = True

    # Used for exchange-confirmation links in emails
    frontend_base_url: str = "http://localhost:3000"

    # Optional fine-tuned CLIP weights (ViT-B/32 state_dict checkpoint)
    clip_ft_checkpoint: str | None = None

settings = Settings()  # type: ignore