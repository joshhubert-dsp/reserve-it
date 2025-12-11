from zoneinfo import ZoneInfo

from pydantic import EmailStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Global app configuration model, automatically loaded from environment variables with
    the same names as the args (case-insensitive).

    Args:
        app_email (str): The email address of the dedicated Google account used for
            resource calendars.
        timezone (ZoneInfo): the IANA timezone to use for displaying all calendars.
        db_echo (bool): Whether resource sqlite databases should echo their operations
            to the console, for debugging purposes. Defaults to False.
    """

    app_email: EmailStr
    timezone: ZoneInfo
    db_echo: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
