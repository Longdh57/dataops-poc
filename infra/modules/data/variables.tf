variable "project_id" { type = string }
variable "region" { type = string }
variable "labels" { type = map(string) }
variable "dataset_id" { type = string }
variable "readers" {
  description = "Service account duoc doc dataset"
  type        = list(string)
  default     = []
}
variable "analytics_dataset_id" {
  description = "Dataset rieng chua ban sao qc_exception (P7)"
  type        = string
  default     = "dataops_analytics"
}
variable "analytics_writers" {
  description = "Service account duoc GHI vao dataset analytics"
  type        = list(string)
  default     = []
}
