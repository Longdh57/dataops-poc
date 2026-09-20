variable "project_id" { type = string }
variable "alert_email" {
  description = "Nhan canh bao. De trong thi khong tao kenh thong bao."
  type        = string
  default     = ""
}
variable "sync_job_name" { type = string }
