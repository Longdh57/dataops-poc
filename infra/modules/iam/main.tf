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
