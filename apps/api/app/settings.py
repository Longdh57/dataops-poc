from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://dataops:dataops@db:5432/dataops"
    gcp_project_id: str = ""
    project_number: str = ""
    bigquery_dataset: str = "dataops_src"
    staging_bucket: str = ""
    region: str = "asia-southeast1"
    # Cloud Run Job ma nut "Nap lai tu nguon" kich hoat
    sync_job_name: str = "dataops-sync"
    # Cloud Run Job sinh file deliverable
    export_job_name: str = "dataops-export"

    # Model Gemini goi qua Vertex AI cho AI Agent (P7). Dung ADC cua
    # service account dataops-api, khong can API key.
    agent_model: str = "gemini-2.5-flash"

    # Bat buoc verify IAP JWT. Chi dat false khi chay local hoac khi
    # IAP chua bat duoc — luc do danh tinh lay tu header X-Dev-User.
    require_iap: bool = False
    # Backend ID de kiem audience cua IAP JWT (chi dung khi require_iap).
    iap_audience: str = ""

    cors_origins: str = "http://localhost:3000"


settings = Settings()
