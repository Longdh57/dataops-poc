variable "project_id" { type = string }
variable "region" { type = string }
variable "labels" {
  type    = map(string)
  default = {}
}
variable "project_number" { type = string }

variable "github_repo" {
  description = "Dang 'owner/repo'. De trong thi bo qua toan bo phan CI/CD."
  type        = string
  default     = ""
}

variable "iap_members" {
  description = "Ai duoc mo ung dung. Vi du ['user:a@gmail.com', 'group:x@googlegroups.com']"
  type        = list(string)
  default     = []
}
