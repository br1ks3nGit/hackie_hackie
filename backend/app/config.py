import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./drivescore.db"
    insurer_api_key: str  # required, no default — set via env or .env
    driver_api_key_salt: str  # required, no default — set via env or .env
    cors_origins: str = "http://localhost:3000,http://localhost:19006"
    data_dir: str = "./data/raw"
    model_path: str = "./models/model.pkl"
    trip_min_distance_km: float = 1.0
    trip_max_gps_gap_s: float = 30.0
    trip_min_duration_s: float = 60.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
