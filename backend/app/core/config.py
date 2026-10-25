from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

class Settings(BaseSettings):
    app_name: str = "DocCraft Member 4 - Batch & Review"
    environment: str = "development"
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "doccraft_member4"
    reliability_threshold: float = 0.80
    mock_processing_delay_seconds: float = 0.5

    model_config = SettingsConfigDict(env_file=".env")

    weight_ocr: float = 0.3
    weight_ai: float = 0.5
    weight_validation: float = 0.2

    @model_validator(mode="after")
    def weights_must_sum_to_one(self):
        total = self.weight_ocr + self.weight_ai + self.weight_validation
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Reliability weights must add up to 1.0, got {total}")
        return self


settings = Settings()