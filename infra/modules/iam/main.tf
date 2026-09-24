locals {
  ci_enabled = var.github_repo != ""
}

# --- Service account cho CI/CD ---

resource "google_service_account" "deployer" {
  count        = local.ci_enabled ? 1 : 0
  project      = var.project_id
  account_id   = "dataops-deployer"
  display_name = "Dataops CI/CD (GitHub Actions)"
}

resource "google_project_iam_member" "deployer" {
  for_each = local.ci_enabled ? toset([
    "roles/run.admin",
    "roles/artifactregistry.writer",
    "roles/cloudbuild.builds.editor",
    "roles/iam.serviceAccountUser",
    "roles/storage.admin",
  ]) : toset([])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer[0].email}"
}

# --- Workload Identity Federation: GitHub doi OIDC token lay quyen GCP ---
# Khong co key file nao duoc tao ra, nen khong co gi de ro ri.

resource "google_iam_workload_identity_pool" "github" {
  count                     = local.ci_enabled ? 1 : 0
  project                   = var.project_id
  workload_identity_pool_id = "github-pool"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count                              = local.ci_enabled ? 1 : 0
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # BAT BUOC: khong co dieu kien nay thi MOI repo tren GitHub deu doi duoc token.
  attribute_condition = "assertion.repository == '${var.github_repo}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_impersonate" {
  count              = local.ci_enabled ? 1 : 0
  service_account_id = google_service_account.deployer[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repo}"
}

# --- IAP: ai duoc mo ung dung ---

resource "google_project_iam_member" "iap_access" {
  for_each = toset(var.iap_members)
  project  = var.project_id
  role     = "roles/iap.httpsResourceAccessor"
  member   = each.value
}

# --- Service account cho tung thanh phan chay ---
#
# Ba tai khoan nay truoc do tao bang gcloud, nam ngoai Terraform. Dua vao
# day de dung lai he thong tu project trong chi can terraform apply.
#
# Du an dang chay phai `terraform import` chung mot lan truoc khi apply —
# xem scripts/import-existing.sh.
#
# CO Y KHONG cap secretmanager.secretAccessor o cap project: quyen do da
# duoc cap dung tren mot secret trong module database. Cap o ca hai cho
# khien viec ra soat "ai doc duoc bi mat nao" tra ve cau tra loi sai.

locals {
  runtime_accounts = {
    api = {
      display = "Dataops API (Cloud Run)"
      # aiplatform.user: goi Gemini qua Vertex AI cho AI Agent (P7).
      # monitoring.viewer: doc metric token_count de hien chi phi Vertex AI
      # thang nay tren man hinh Agent (xem app/agent/usage.py). Chi DOC
      # metric, khong cho ghi va khong dung toi du lieu nghiep vu nao.
      roles = ["roles/bigquery.dataViewer", "roles/bigquery.jobUser", "roles/cloudsql.client",
      "roles/aiplatform.user", "roles/monitoring.viewer"]
    }
    jobs = {
      display = "Dataops Jobs (Sync, QC, Export)"
      roles   = ["roles/bigquery.dataViewer", "roles/bigquery.jobUser", "roles/cloudsql.client"]
    }
    # Web khong doc du lieu: no chi goi API bang OIDC token, va quyen do
    # la binding tren service API chu khong phai vai tro cap project.
    web = {
      display = "Dataops Web (Cloud Run)"
      roles   = []
    }
  }

  runtime_bindings = merge([
    for key, acc in local.runtime_accounts : {
      for role in acc.roles : "${key}:${role}" => { key = key, role = role }
    }
  ]...)
}

resource "google_service_account" "runtime" {
  for_each     = local.runtime_accounts
  project      = var.project_id
  account_id   = "dataops-${each.key}"
  display_name = each.value.display
}

resource "google_project_iam_member" "runtime" {
  for_each = local.runtime_bindings
  project  = var.project_id
  role     = each.value.role
  member   = "serviceAccount:${google_service_account.runtime[each.value.key].email}"
}
