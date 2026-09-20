from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://dataops:dataops@db:5432/dataops"
    gcp_project_id: str = ""
    bigquery_dataset: str = ""
    # Local dev bo qua IAP; tren Cloud Run bat len de bat buoc verify JWT.
    require_iap: bool = False
    cors_origins: str = "http://localhost:3000"


settings = Settings()
