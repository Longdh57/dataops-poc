# Dataset tren BigQuery.
#
# Terraform tao cai HOP, khong tao du lieu ben trong: bang fact la viec cua
# team Data, ung dung chi doc. Rieng moi truong demo thi Cloud Run Job
# dataops-seed dung mot bang mau tu du lieu cong khai — chay tay, khong
# nam trong duong chay hang ngay.

resource "google_bigquery_dataset" "src" {
  project                    = var.project_id
  dataset_id                 = var.dataset_id
  location                   = var.region
  labels                     = var.labels
  description                = "Nguon su that cua ung dung. Team Data ghi, ung dung chi doc."
  delete_contents_on_destroy = false # du lieu nguon khong bien mat theo terraform destroy
}

resource "google_bigquery_dataset_iam_member" "readers" {
  for_each   = toset(var.readers)
  project    = var.project_id
  dataset_id = google_bigquery_dataset.src.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${each.value}"
}
