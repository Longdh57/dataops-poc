from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://dataops:dataops@db:5432/dataops"
    gcp_project_id: str = ""
    project_number: str = ""
    bigquery_dataset: str = "dataops_src"
    # Bang fact nguon — team Data ghi, ung dung chi doc.
    bigquery_table: str = "fact_names"
    # Dataset RIENG chua snapshot cua moi ban ky (xem docs/thiet-ke-ky-du-lieu.md).
    # Tach khoi dataset nguon: ung dung ghi duoc o day, team Data thi khong.
    bigquery_signed_dataset: str = "dataops_signed"
    staging_bucket: str = ""
    region: str = "asia-southeast1"
    # Cloud Run Job ma nut "Refresh table" kich hoat
    sync_job_name: str = "dataops-sync"
    # Cloud Run Job sinh file deliverable
    export_job_name: str = "dataops-export"
    # Cloud Run Job QC Runner — nut "Chay QC ngay" trong hop Bo luat (P10)
    qc_job_name: str = "dataops-qc"

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
