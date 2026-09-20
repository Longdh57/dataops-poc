variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Vung trien khai chinh"
  type        = string
  default     = "asia-southeast1"
}

variable "env" {
  description = "Ten moi truong, dung lam label de boc chi phi"
  type        = string
  default     = "poc"
}

variable "api_service_account" {
  description = "Service account ma Cloud Run API chay duoi"
  type        = string
}

variable "api_image" {
  description = "Anh cua API. De mac dinh khi chua build lan nao."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "web_image" {
  description = "Anh cua Web"
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "github_repo" {
  description = "'owner/repo' de bat CI/CD. De trong thi bo qua."
  type        = string
  default     = ""
}

variable "iap_members" {
  description = "Ai duoc mo ung dung qua IAP"
  type        = list(string)
  default     = []
}

variable "iap_enabled" {
  description = "Bat IAP. Can OAuth client — xem README phan 'Bat IAP'."
  type        = bool
  default     = false
}

variable "web_service_account" {
  description = "Service account ma Cloud Run Web chay duoi"
  type        = string
}

variable "public_access" {
  description = "NO KY THUAT — mo web cho allUsers. Dat lai false truoc P2."
  type        = bool
  default     = false
}

variable "jobs_service_account" {
  description = "Service account cua Sync Job va Export Job"
  type        = string
}

variable "jobs_image" {
  description = "Anh cua Sync Job / Export Job"
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "bq_dataset" {
  description = "Dataset BigQuery dong vai nguon su that"
  type        = string
  default     = "dataops_src"
}

variable "alert_email" {
  description = "Email nhan canh bao dong bo tre"
  type        = string
  default     = ""
}
