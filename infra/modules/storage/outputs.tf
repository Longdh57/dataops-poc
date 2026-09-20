output "bucket" {
  value = google_storage_bucket.staging.name
}
output "bucket_url" {
  value = google_storage_bucket.staging.url
}
