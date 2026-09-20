output "instance_name" {
  value = google_sql_database_instance.main.name
}

output "connection_name" {
  description = "Dung cho Cloud SQL Auth Proxy khi dev local"
  value       = google_sql_database_instance.main.connection_name
}

output "private_ip" {
  value = google_sql_database_instance.main.private_ip_address
}

output "db_url_secret_id" {
  value = google_secret_manager_secret.db_url.secret_id
}

output "secret_iam_ready" {
  description = "Chan de runtime depends_on, dam bao quyen co truoc khi deploy"
  value       = join(",", [for k, v in google_secret_manager_secret_iam_member.accessors : v.etag])
}
