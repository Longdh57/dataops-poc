# Noi BigQuery EXPORT DATA ghi parquet, va noi Export Job dat file gui khach.
resource "google_storage_bucket" "staging" {
  project                     = var.project_id
  name                        = "${var.project_id}-staging"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true # PoC: cho phep destroy sach
  labels                      = var.labels

  # File trung chuyen khong giu lau — tranh phinh chi phi luu tru.
  lifecycle_rule {
    condition { age = 7 }
    action { type = "Delete" }
  }
}

resource "google_storage_bucket_iam_member" "writers" {
  for_each = toset(var.writers)
  bucket   = google_storage_bucket.staging.name
  role     = "roles/storage.objectAdmin"
  member   = "serviceAccount:${each.value}"
}

# URL ky san uy quyen theo danh tinh NGUOI KY, khong phai nguoi bam link.
# API ky URL tai file nen ban than no phai doc duoc object — thieu cai nay
# thi URL ky ra van hop le nhung GCS tra 403. Chi doc, khong ghi: viec ghi
# file la cua Export Job.
resource "google_storage_bucket_iam_member" "readers" {
  for_each = toset(var.readers)
  bucket   = google_storage_bucket.staging.name
  role     = "roles/storage.objectViewer"
  member   = "serviceAccount:${each.value}"
}
