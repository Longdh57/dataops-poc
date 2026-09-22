output "dataset_id" {
  value = google_bigquery_dataset.src.dataset_id
}
output "analytics_dataset_id" {
  value = google_bigquery_dataset.analytics.dataset_id
}
