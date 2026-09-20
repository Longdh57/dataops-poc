variable "project_id" { type = string }
variable "region" { type = string }
variable "labels" {
  type    = map(string)
  default = {}
}
variable "network_id" {
  description = "VPC de gan private IP"
  type        = string
}
variable "psa_connection" {
  description = "Chan de ep thu tu: phai co peering truoc khi tao instance"
  type        = string
}

variable "secret_accessors" {
  description = "Service account duoc doc connection string. Gan o cap secret, khong phai cap project."
  type        = list(string)
  default     = []
}
