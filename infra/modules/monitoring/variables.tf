variable "project_id" { type = string }
variable "alert_email" {
  description = "Nhan canh bao. De trong thi khong tao kenh thong bao."
  type        = string
  default     = ""
}
variable "sync_job_name" { type = string }
variable "qc_job_name" { type = string }
variable "export_job_name" { type = string }
variable "web_url" {
  description = "URL uptime check go vao. De trong thi bo qua uptime check."
  type        = string
  default     = ""
}
