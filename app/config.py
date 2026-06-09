import warnings
from pathlib import Path

from pydantic import model_validator
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

    @model_validator(mode="after")
    def _warn_credentials_in_project_dir(self) -> "Settings":
        cwd = Path.cwd().resolve()
        for path_str, label in [
            (self.google_credentials_path, "google_credentials_path"),
            (self.google_token_path, "google_token_path"),
        ]:
            try:
                Path(path_str).resolve().relative_to(cwd)
                if Path(path_str).exists():
                    warnings.warn(
                        f"[SubFlow] {label}={path_str!r} is inside the project directory. "
                        "Consider moving it to an external path to reduce accidental exposure.",
                        stacklevel=2,
                    )
            except ValueError:
                pass
        return self


settings = Settings()
