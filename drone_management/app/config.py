from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_url: str = Field(default="sqlite+aiosqlite:///./drone_management.db", alias="DB_URL")

    mavlink_bind_host: str = Field(default="0.0.0.0", alias="MAVLINK_BIND_HOST")
    mavlink_bind_port: int = Field(default=14550, alias="MAVLINK_BIND_PORT")
    drone_host: str = Field(default="127.0.0.1", alias="DRONE_HOST")
    drone_port: int = Field(default=14551, alias="DRONE_PORT")

    http_host: str = Field(default="127.0.0.1", alias="HTTP_HOST")
    http_port: int = Field(default=8000, alias="HTTP_PORT")

    gcs_system_id: int = Field(default=255, alias="GCS_SYSTEM_ID")
    gcs_component_id: int = Field(default=190, alias="GCS_COMPONENT_ID")


settings = Settings()
