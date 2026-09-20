# Ten instance khong tai su dung duoc trong ~7 ngay sau khi xoa,
# nen gan hau to ngau nhien de dung lai duoc ngay.
resource "random_id" "suffix" {
  byte_length = 2
}

resource "random_password" "app" {
  length  = 32
  special = false # tranh ky tu phai escape trong connection string
}

resource "google_sql_database_instance" "main" {
  project          = var.project_id
  name             = "dataops-pg-${random_id.suffix.hex}"
  region           = var.region
  database_version = "POSTGRES_17"

  # PoC: cho phep destroy de kiem chung "dung lai tu project trong".
  # Len production doi thanh true.
  deletion_protection = false

  settings {
    # POSTGRES_17 mac dinh ENTERPRISE_PLUS, ma edition do khong co tier
    # shared-core. Phai khai bao ENTERPRISE de dung duoc db-f1-micro.
    edition           = "ENTERPRISE"
    tier              = "db-f1-micro"
    availability_type = "ZONAL" # khong HA — HA nhan doi gia
    disk_type         = "PD_HDD"
    disk_size         = 10
    disk_autoresize   = true

    user_labels = var.labels

    ip_configuration {
      ipv4_enabled    = false # KHONG co public IP
      private_network = var.network_id
    }

    backup_configuration {
      enabled    = true
      start_time = "18:00" # UTC = 01:00 gio VN, luc khong ai dung

      backup_retention_settings {
        retained_backups = 2
        retention_unit   = "COUNT"
      }
    }

    maintenance_window {
      day          = 7 # chu nhat
      hour         = 19 # 02:00 gio VN
      update_track = "stable"
    }

    insights_config {
      query_insights_enabled = true
    }
  }

  depends_on = [var.psa_connection]
}

resource "google_sql_database" "app" {
  project  = var.project_id
  name     = "dataops"
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "app" {
  project  = var.project_id
  name     = "dataops"
  instance = google_sql_database_instance.main.name
  password = random_password.app.result
}

# --- Connection string di vao Secret Manager, khong vao bien moi truong ---

resource "google_secret_manager_secret" "db_url" {
  project   = var.project_id
  secret_id = "dataops-database-url"
  labels    = var.labels

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_url" {
  secret = google_secret_manager_secret.db_url.id
  secret_data = format(
    "postgresql://%s:%s@%s:5432/%s",
    google_sql_user.app.name,
    random_password.app.result,
    google_sql_database_instance.main.private_ip_address,
    google_sql_database.app.name,
  )
}

# Quyen gan thang vao secret nay — hep hon cap project, va tao ra
# quan he phu thuoc ro rang de Cloud Run khong chay truoc khi co quyen.
resource "google_secret_manager_secret_iam_member" "accessors" {
  for_each  = toset(var.secret_accessors)
  project   = var.project_id
  secret_id = google_secret_manager_secret.db_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value}"
}
