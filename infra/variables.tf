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
