# Rui ro lon nhat cua kien truc nay: Sync Job chet am tham, ban sao cu dan
# ma khong ai biet. Do dem "so lan sync thanh cong"; vang mat qua 30 phut
# la co van de.

resource "google_logging_metric" "sync_success" {
  project = var.project_id
  name    = "dataops/sync_success"
  filter  = <<-EOT
    resource.type="cloud_run_job"
    resource.labels.job_name="${var.sync_job_name}"
    textPayload=~"^\\[sync\\] (XONG|nguon khong doi)"
  EOT

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }
}

resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email == "" ? 0 : 1
  project      = var.project_id
  display_name = "Dataops alerts"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

resource "google_monitoring_alert_policy" "sync_stale" {
  count        = var.alert_email == "" ? 0 : 1
  project      = var.project_id
  display_name = "Sync Job im lang qua 30 phut"
  combiner     = "OR"
  severity     = "WARNING"

  conditions {
    display_name = "Khong co lan sync thanh cong nao trong 30 phut"

    condition_absent {
      filter   = "resource.type=\"cloud_run_job\" AND metric.type=\"logging.googleapis.com/user/${google_logging_metric.sync_success.name}\""
      duration = "1800s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  documentation {
    content = <<-EOT
      Sync Job khong bao cao thanh cong trong 30 phut.

      Hau qua: ban sao trong Cloud SQL cu dan ma giao dien khong bao gi.
      Luong export gui khach van doc thang BigQuery nen so gui khach
      KHONG bi anh huong — nhung moi thu tren man hinh thi co.

      Kiem tra:
        gcloud run jobs executions list --job=${var.sync_job_name} --region=asia-southeast1
        gcloud scheduler jobs describe dataops-sync-every-60s --location=asia-southeast1
    EOT
    mime_type = "text/markdown"
  }
}
