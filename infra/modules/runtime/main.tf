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

      # API kich hoat hai job nay. Truyen ten tu Terraform chu khong de API
      # doan theo mac dinh: doi ten job ben nay ma ben kia khong biet thi
      # nut bam se hong lang le.
      env {
        name  = "REGION"
        value = var.region
      }

      env {
        name  = "SYNC_JOB_NAME"
        value = google_cloud_run_v2_job.sync.name
      }

      env {
        name  = "EXPORT_JOB_NAME"
        value = google_cloud_run_v2_job.export.name
      }

      # P10: nut "Chay QC ngay" trong hop Bo luat
      env {
        name  = "QC_JOB_NAME"
        value = google_cloud_run_v2_job.qc.name
      }

      # P11: ky = chup bang fact nguon thanh snapshot trong dataset rieng.
      env {
        name  = "BIGQUERY_DATASET"
        value = var.bq_dataset
      }

      env {
        name  = "BIGQUERY_SIGNED_DATASET"
        value = var.bq_signed_dataset
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
    GCP_PROJECT_ID = var.project_id
    BQ_DATASET     = var.bq_dataset
    BQ_TABLE       = "fact_names"
    BQ_LOCATION    = var.region
    STAGING_BUCKET = var.staging_bucket
    WORKDIR        = "/tmp/sync"
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

# QC Runner — ap bo luat len fact_current. Tu P10 bo luat doc tu Postgres
# (bang qc_rule), khong con doc file rules/rules.yaml.
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

        # P7: sau moi lan quet, day anh chup qc_exception len BigQuery cho
        # bao cao/BI phia khach hang. Ung dung van doc/ghi qua Postgres —
        # day chi la mot chieu ban sao, khong doi duong doc de tiet kiem
        # chi phi query.
        env {
          name  = "MIRROR_QC_TO_BIGQUERY"
          value = "1"
        }
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "BQ_ANALYTICS_DATASET"
          value = var.bq_analytics_dataset
        }
        env {
          name  = "BQ_LOCATION"
          value = var.region
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

# --- Export Job: sinh file deliverable tu ban da ky ---
#
# Khong co Scheduler nao goi job nay: API kich hoat truc tiep khi co nguoi
# bam "Gui yeu cau", kem EXPORT_JOB_ID de job chi xu ly dung yeu cau do.
# Poll dinh ky se lam nguoi dung cho vo co toi vai phut du hang doi rong.

resource "google_cloud_run_v2_job" "export" {
  project             = var.project_id
  name                = "dataops-export"
  location            = var.region
  labels              = var.labels
  deletion_protection = false

  template {
    template {
      service_account = var.jobs_service_account
      max_retries     = 0 # job tu ghi trang thai 'error' vao DB, retry chi ton tien
      timeout         = "1800s"

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
        args    = ["export/main.py"]

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

        # Sinh xlsx cho ca trieu dong can nhieu RAM hon CSV.
        resources {
          limits = { cpu = "2", memory = "4Gi" }
        }
      }
    }
  }

  depends_on = [terraform_data.secret_gate]

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
}

# API la thu kich hoat Export Job va Sync Job, nen no phai duoc phep chay
# hai job do. Day la quyen duy nhat API co tren Cloud Run.
#
# KHONG phai run.invoker. API goi Export Job kem overrides de truyen
# EXPORT_JOB_ID, ma run.invoker chi co run.jobs.run — thieu dung cai
# run.jobs.runWithOverrides, nen Cloud Run tra 403 va yeu cau nam mai
# trong hang doi. jobsExecutorWithOverrides la role hep nhat co ca hai:
#
#   gcloud iam roles describe roles/run.jobsExecutorWithOverrides
#   -> run.executions.cancel, run.jobs.run, run.jobs.runWithOverrides
resource "google_cloud_run_v2_job_iam_member" "api_invoke_export" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.export.name
  role     = "roles/run.jobsExecutorWithOverrides"
  member   = "serviceAccount:${var.api_service_account}"
}

# Sync Job thi van la run.invoker: API goi no KHONG kem overrides
# (app/main.py, run_job(settings.sync_job_name) khong truyen env), nen
# them quyen o day chi la cap thua.
resource "google_cloud_run_v2_job_iam_member" "api_invoke_sync" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.sync.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.api_service_account}"
}

# P10: API goi QC Runner kem FORCE_QC=1 (ep chay lai du run khong doi),
# tuc la co overrides — cung ly do voi export job o tren, run.invoker
# khong du.
resource "google_cloud_run_v2_job_iam_member" "api_invoke_qc" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.qc.name
  role     = "roles/run.jobsExecutorWithOverrides"
  member   = "serviceAccount:${var.api_service_account}"
}

# API phai ky duoc URL tai file. Service account tren Cloud Run khong giu
# private key nen khong ky offline duoc — no goi IAM SignBlob de tu ky cho
# chinh minh (app/main.py, signed_url). Muon vay thi phai duoc lam
# tokenCreator TREN CHINH NO. Thieu binding nay thi job sinh file xong
# nhung nut tai ve tra 503 "chua ky duoc URL".
#
# Binding nay nam o module.runtime chu khong phai module.iam: module.iam
# la noi TAO service account, doi chieu nguoc lai se thanh vong phu thuoc.
resource "google_service_account_iam_member" "api_self_sign" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${var.api_service_account}"
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${var.api_service_account}"
}

# --- Seed: nguoi dung thu nghiem va du lieu demo ---
#
# Khong co Scheduler. Chay tay dung mot lan khi dung moi truong moi:
#   gcloud run jobs execute dataops-seed --region=<region>
#
# Mac dinh chi seed nguoi dung. Muon dung luon bang fact demo tren BigQuery
# thi them --update-env-vars=SEED_BIGQUERY=1 — buoc do thuoc ve Data
# Engineer o du an that.

resource "google_cloud_run_v2_job" "seed" {
  project             = var.project_id
  name                = "dataops-seed"
  location            = var.region
  labels              = var.labels
  deletion_protection = false

  template {
    template {
      service_account = var.jobs_service_account
      max_retries     = 0
      timeout         = "1800s"

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
        args    = ["seed/main.py"]

        dynamic "env" {
          for_each = local.job_env
          content {
            name  = env.key
            value = env.value
          }
        }

        env {
          name  = "OWNER_EMAIL"
          value = var.owner_email
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
