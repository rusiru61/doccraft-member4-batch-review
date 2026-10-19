from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DocCraft Member 4 - Batch & Review"
    environment: str = "development"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "doccraft_member4"
    reliability_threshold: float = 0.80

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()