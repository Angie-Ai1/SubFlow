from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # MySQL
    mysql_host: str = "db"
    mysql_port: int = 3306
    mysql_database: str = "subflow"
    mysql_user: str = "subflow_user"
    mysql_password: str = ""
    database_url: str = ""

    # LINE Bot
    line_channel_access_token: str = ""
    line_channel_secret: str = ""

    # Google / Gmail
    google_credentials_path: str = "credentials.json"
    google_token_path: str = "token.json"
    gmail_target_address: str = ""

    # Scheduler / notifications
    notify_days_advance: int = 3
    cron_notification_hour: int = 9


settings = Settings()
