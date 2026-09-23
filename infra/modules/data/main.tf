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

# Dataset RIENG chua snapshot cua moi ban ky (P11) — xem
# docs/thiet-ke-ky-du-lieu.md. Ung dung GHI o day (API tao snapshot luc
# ky), team Data thi khong: ban da ky khong duoc de ai sua sau lung. Tach
# khoi "src" de dataset nguon van giu nguyen tac "ung dung chi doc".
#
# KHONG dat default_table_expiration: snapshot phai song cung ban ky, vi
# file gui khach phai tai tao duoc bat cu luc nao.
resource "google_bigquery_dataset" "signed" {
  project                    = var.project_id
  dataset_id                 = var.signed_dataset_id
  location                   = var.region
  labels                     = var.labels
  description                = "Snapshot bang fact tai moi lan ky. Export chi doc tu day. KHONG xoa tay."
  delete_contents_on_destroy = false # mat snapshot = mat bang chung da gui khach so nao
}

resource "google_bigquery_dataset_iam_member" "signed_writers" {
  for_each   = toset(var.signed_writers)
  project    = var.project_id
  dataset_id = google_bigquery_dataset.signed.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${each.value}"
}

resource "google_bigquery_dataset_iam_member" "signed_readers" {
  for_each   = toset(var.signed_readers)
  project    = var.project_id
  dataset_id = google_bigquery_dataset.signed.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${each.value}"
}

resource "google_bigquery_dataset_iam_member" "analytics_writers" {
  for_each   = toset(var.analytics_writers)
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${each.value}"
}
