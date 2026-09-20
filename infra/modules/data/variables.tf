variable "project_id" { type = string }
variable "region" { type = string }
variable "labels" { type = map(string) }
variable "dataset_id" { type = string }
variable "readers" {
  description = "Service account duoc doc dataset"
  type        = list(string)
  default     = []
}
