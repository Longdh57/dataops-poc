output "project_id" {
  value = data.google_project.this.project_id
}

output "project_number" {
  value = data.google_project.this.number
}

output "sql_instance" {
  value = module.database.instance_name
}

output "sql_private_ip" {
  value = module.database.private_ip
}

output "sql_connection_name" {
  value = module.database.connection_name
}

output "registry" {
  value = module.runtime.registry
}

output "api_url" {
  value = module.runtime.api_url
}

output "web_url" {
  value = module.runtime.web_url
}

output "workload_identity_provider" {
  value = module.iam.workload_identity_provider
}

output "deployer_email" {
  value = module.iam.deployer_email
}
