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

# Dataset RIENG cho ban sao qc_exception (P7) — khac han dataset "src" o
# tren: cai nay ung dung ghi, phia khach hang doc de bao cao/BI. Tach
# rieng de khong pha nguyen tac "team Data ghi, ung dung chi doc" cua
# dataset nguon.
resource "google_bigquery_dataset" "analytics" {
  project                    = var.project_id
  dataset_id                 = var.analytics_dataset_id
  location                   = var.region
  labels                     = var.labels
  description                = "Ban sao qc_exception tu Postgres, chi de bao cao — ung dung van doc/ghi qua Postgres."
  delete_contents_on_destroy = true # chi la ban sao, mat thi day lai duoc
}

resource "google_bigquery_dataset_iam_member" "analytics_writers" {
  for_each   = toset(var.analytics_writers)
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${each.value}"
}
