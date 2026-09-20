output "registry" {
  value = "${google_artifact_registry_repository.images.location}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "api_url" {
  value = google_cloud_run_v2_service.api.uri
}

output "web_url" {
  value = google_cloud_run_v2_service.web.uri
}

output "api_name" {
  value = google_cloud_run_v2_service.api.name
}

output "web_name" {
  value = google_cloud_run_v2_service.web.name
}
