variable "project_id" { type = string }
variable "region" { type = string }
variable "labels" {
  type    = map(string)
  default = {}
}
variable "network_id" { type = string }
variable "subnet_id" { type = string }
variable "db_url_secret_id" { type = string }
variable "api_service_account" { type = string }

# Anh placeholder cua Google de dung service lan dau khi chua build gi.
# CI/CD se ghi de bang anh that.
variable "api_image" {
  type    = string
  default = "us-docker.pkg.dev/cloudrun/container/hello"
}
variable "web_image" {
  type    = string
  default = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "project_number" {
  description = "Can de dung email cua IAP service agent"
  type        = string
}

variable "secret_iam_ready" {
  description = "Chi de ep thu tu — khong dung vao dau"
  type        = string
  default     = ""
}

variable "iap_enabled" {
  description = "Chi bat duoc khi da co OAuth client. Project khong thuoc Organization thi phai tao tay trong Console."
  type        = bool
  default     = false
}

variable "web_service_account" {
  description = "Service account ma Cloud Run Web chay duoi"
  type        = string
}

variable "public_access" {
  description = "NO KY THUAT — mo web cho allUsers. Phai dat lai false truoc P2."
  type        = bool
  default     = false
}

variable "jobs_service_account" {
  description = "Service account cua Sync Job va Export Job"
  type        = string
}
variable "jobs_image" {
  type    = string
  default = "us-docker.pkg.dev/cloudrun/container/hello"
}
variable "staging_bucket" {
  type    = string
  default = ""
}
variable "bq_dataset" {
  type    = string
  default = "dataops_src"
}
variable "bq_signed_dataset" {
  description = "Dataset chua snapshot ban ky — API ghi luc ky (P11)"
  type        = string
  default     = "dataops_signed"
}
variable "bq_analytics_dataset" {
  description = "Dataset QC Job day ban sao qc_exception vao (P7)"
  type        = string
  default     = "dataops_analytics"
}
variable "owner_email" {
  description = "Tai khoan duoc seed voi vai tro admin"
  type        = string
  default     = ""
}
