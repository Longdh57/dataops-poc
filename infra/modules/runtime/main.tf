# Chan phu thuoc: Cloud Run khong duoc tao truoc khi quyen doc secret co hieu luc.
resource "terraform_data" "secret_gate" {
  input = var.secret_iam_ready
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = "dataops"
  format        = "DOCKER"
  description   = "Image cua web, api va jobs"
  labels        = var.labels

  # Giu 5 ban gan nhat, xoa phan con lai — tranh phinh dung luong.
  cleanup_policies {
    id     = "giu-5-ban-moi-nhat"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }
}

# --- API ---

resource "google_cloud_run_v2_service" "api" {
  project             = var.project_id
  name                = "dataops-api"
  location            = var.region
  labels              = var.labels
  deletion_protection = false

  ingress     = "INGRESS_TRAFFIC_ALL"
  iap_enabled = var.iap_enabled

  template {
    service_account = var.api_service_account

    scaling {
      min_instance_count = 0 # scale-to-zero: khong ai dung thi khong ton tien
      max_instance_count = 3
    }

    # Direct VPC egress — noi thang vao VPC, khong can Serverless VPC connector
    # (connector chay 2 instance thuong truc, ton them ~250k/thang).
    vpc_access {
      network_interfaces {
        network    = var.network_id
        subnetwork = var.subnet_id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = var.api_image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = var.db_url_secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      # Phai di cung iap_enabled: bat REQUIRE_IAP khi IAP chua bat thi
      # moi request deu 401 vi khong co assertion nao ca.
      env {
        name  = "REQUIRE_IAP"
        value = var.iap_enabled ? "true" : "false"
      }
    }
  }

  depends_on = [terraform_data.secret_gate]

  lifecycle {
    # CI/CD deploy anh moi; terraform khong duoc keo nguoc lai anh cu.
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
}

# --- WEB ---

resource "google_cloud_run_v2_service" "web" {
  project             = var.project_id
  name                = "dataops-web"
  location            = var.region
  labels              = var.labels
  deletion_protection = false

  ingress     = "INGRESS_TRAFFIC_ALL"
  iap_enabled = var.iap_enabled

  template {
    service_account = var.web_service_account

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.web_image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }

      env {
        name  = "API_URL"
        value = google_cloud_run_v2_service.api.uri
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
}

# --- IAP: cho phep IAP goi vao hai service ---
# Khong co hai binding nay thi IAP xac thuc xong van khong vao duoc (403).

locals {
  iap_agent = "serviceAccount:service-${var.project_number}@gcp-sa-iap.iam.gserviceaccount.com"
}

resource "google_cloud_run_v2_service_iam_member" "iap_invoker_api" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = local.iap_agent
}

resource "google_cloud_run_v2_service_iam_member" "iap_invoker_web" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.invoker"
  member   = local.iap_agent
}

# Web goi API server-side bang ID token -> can quyen invoke.
resource "google_cloud_run_v2_service_iam_member" "web_calls_api" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.web_service_account}"
}

# ============================================================
# NO KY THUAT — TAM THOI
# Mo web cho moi nguoi vi IAP chua bat duoc (project khong thuoc
# Organization). Chi WEB duoc mo; API van dong kin va chi web goi
# duoc bang OIDC token.
# PHAI dat public_access = false truoc P2, khi du lieu that do vao.
# ============================================================
resource "google_cloud_run_v2_service_iam_member" "public_web" {
  count    = var.public_access ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ==================== JOBS ====================

locals {
  job_env = {
    GCP_PROJECT_ID  = var.project_id
    BQ_DATASET      = var.bq_dataset
    BQ_TABLE        = "fact_names"
    BQ_LOCATION     = var.region
    STAGING_BUCKET  = var.staging_bucket
    WORKDIR         = "/tmp/sync"
  }
}

# Migration chay TU TRONG VPC — Cloud SQL chi co private IP nen khong
# the chay alembic tu may ca nhan.
resource "google_cloud_run_v2_job" "migrate" {
  project             = var.project_id
  name                = "dataops-migrate"
  location            = var.region
  labels              = var.labels
  deletion_protection = false

  template {
    template {
      service_account = var.api_service_account
      max_retries     = 1
      timeout         = "600s"

      vpc_access {
        network_interfaces {
          network    = var.network_id
          subnetwork = var.subnet_id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image   = var.api_image
        command = ["alembic"]
        args    = ["upgrade", "head"]

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = var.db_url_secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
}

resource "google_cloud_run_v2_job" "sync" {
  project             = var.project_id
  name                = "dataops-sync"
  location            = var.region
  labels              = var.labels
  deletion_protection = false

  template {
    template {
      service_account = var.jobs_service_account
      max_retries     = 1
      timeout         = "900s"

      vpc_access {
        network_interfaces {
          network    = var.network_id
          subnetwork = var.subnet_id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image = var.jobs_image

        dynamic "env" {
          for_each = local.job_env
          content {
            name  = env.key
            value = env.value
          }
        }

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = var.db_url_secret_id
              version = "latest"
            }
          }
        }

        resources {
          limits = {
            cpu    = "2"
            memory = "2Gi"
          }
        }
      }
    }
  }

  depends_on = [terraform_data.secret_gate]

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
}

# Scheduler goi Sync Job moi 60 giay — chu ky ngan nhat Cloud Scheduler ho tro.
resource "google_cloud_scheduler_job" "sync" {
  project     = var.project_id
  name        = "dataops-sync-every-60s"
  region      = var.region
  schedule    = "* * * * *"
  time_zone   = "Asia/Ho_Chi_Minh"
  description = "Kich hoat Sync Job kiem tra metadata BigQuery"

  attempt_deadline = "320s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.sync.name}:run"

    oauth_token {
      service_account_email = var.jobs_service_account
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
}

# Scheduler phai duoc phep chay job
resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.sync.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.jobs_service_account}"
}

# QC Runner — ap bo luat trong rules/rules.yaml len fact_current.
resource "google_cloud_run_v2_job" "qc" {
  project             = var.project_id
  name                = "dataops-qc"
  location            = var.region
  labels              = var.labels
  deletion_protection = false

  template {
    template {
      service_account = var.jobs_service_account
      max_retries     = 1
      timeout         = "900s"

      vpc_access {
        network_interfaces {
          network    = var.network_id
          subnetwork = var.subnet_id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image   = var.jobs_image
        command = ["python"]
        args    = ["qc/main.py"]

        env {
          name  = "RULES_PATH"
          value = "/srv/rules/rules.yaml"
        }

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = var.db_url_secret_id
              version = "latest"
            }
          }
        }

        resources {
          limits = { cpu = "1", memory = "1Gi" }
        }
      }
    }
  }

  depends_on = [terraform_data.secret_gate]

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
}

resource "google_cloud_scheduler_job" "qc" {
  project     = var.project_id
  name        = "dataops-qc-every-5m"
  region      = var.region
  schedule    = "*/5 * * * *"
  time_zone   = "Asia/Ho_Chi_Minh"
  description = "Chay lai bo luat QC; tu bo qua neu run chua doi"

  attempt_deadline = "320s"
  retry_config { retry_count = 1 }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.qc.name}:run"
    oauth_token {
      service_account_email = var.jobs_service_account
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker_qc" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.qc.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.jobs_service_account}"
}
