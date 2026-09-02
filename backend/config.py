from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_hostname: str
    database_port: int
    database_name: str
    database_username: str
    database_password: str
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int

    # Optional SMTP — if unset, emails go to backend/mail_outbox/.
    # When set, failed SMTP does not fall back to outbox.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "AMAlost <noreply@ama.edu.ph>"
    smtp_tls: bool = True

    # Used for exchange-confirmation links in emails
    frontend_base_url: str = "http://localhost:3000"

    # Optional fine-tuned CLIP weights (ViT-B/32 state_dict checkpoint)
    clip_ft_checkpoint: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()  # type: ignore