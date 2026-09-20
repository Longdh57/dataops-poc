variable "project_id" { type = string }
variable "region" { type = string }
variable "labels" {
  type    = map(string)
  default = {}
}
variable "writers" {
  description = "Service account duoc ghi vao bucket. Gan o CAP BUCKET, khong phai cap project."
  type        = list(string)
  default     = []
}
