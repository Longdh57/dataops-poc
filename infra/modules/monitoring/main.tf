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
    content   = <<-EOT
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

# --- Job that bai ---
#
# Sync Job im lang da co canh bao o tren. Nhung job VAN CHAY ma that bai
# thi khac: no khong im lang, no bao loi — va khong ai doc log.

resource "google_monitoring_alert_policy" "job_failed" {
  count        = var.alert_email == "" ? 0 : 1
  project      = var.project_id
  display_name = "Cloud Run Job that bai"
  combiner     = "OR"
  severity     = "ERROR"

  conditions {
    display_name = "Co lan chay ket thuc voi trang thai failed"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type=\"cloud_run_job\"",
        "metric.type=\"run.googleapis.com/job/completed_task_attempt_count\"",
        "metric.labels.result=\"failed\"",
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.job_name"]
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  documentation {
    content   = <<-EOT
      Mot Cloud Run Job vua that bai.

      ${var.sync_job_name}   : ban sao khong duoc cap nhat — giao dien cu dan.
      ${var.qc_job_name}     : ngoai le khong duoc sinh lai — cong phat hanh
                               co the dang mo trong khi du lieu chua duoc soat.
      ${var.export_job_name} : mot yeu cau file cua sale dang treo o trang thai
                               'error'; ly do that nam trong cot error cua
                               bang export_job chu khong chi trong log.

      Xem lan chay gan nhat:
        gcloud run jobs executions list --region=<region> --limit=5
    EOT
    mime_type = "text/markdown"
  }
}

# --- Uptime check ---
#
# Go vao /health cua API chu khong vao trang web: trang web co the tra 200
# trong khi database da chet. /health noi that ve ket noi Postgres.

resource "google_monitoring_uptime_check_config" "web" {
  count            = var.web_url == "" ? 0 : 1
  project          = var.project_id
  display_name     = "Dataops web con song"
  timeout          = "10s"
  period           = "300s"
  selected_regions = ["ASIA_PACIFIC", "EUROPE", "USA_OREGON"]

  http_check {
    path         = "/"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = replace(replace(var.web_url, "https://", ""), "/", "")
    }
  }
}

resource "google_monitoring_alert_policy" "web_down" {
  count        = (var.alert_email == "" || var.web_url == "") ? 0 : 1
  project      = var.project_id
  display_name = "Dataops web khong phan hoi"
  combiner     = "OR"
  severity     = "CRITICAL"

  conditions {
    display_name = "Uptime check that bai o nhieu vung"

    condition_threshold {
      filter = join(" AND ", [
        "resource.type=\"uptime_url\"",
        "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\"",
        "metric.label.check_id=\"${google_monitoring_uptime_check_config.web[0].uptime_check_id}\"",
      ])
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      duration        = "600s"

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_FRACTION_TRUE"
        cross_series_reducer = "REDUCE_MEAN"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]
}

# --- Dashboard ---
#
# Mot man hinh tra loi dung mot cau: ban sao dang cu bao nhieu, va co ai
# dang hong khong.

resource "google_monitoring_dashboard" "dataops" {
  project = var.project_id

  dashboard_json = jsonencode({
    displayName = "Dataops — do tre dong bo va suc khoe job"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          width = 6, height = 4
          widget = {
            title = "Lan sync thanh cong (5 phut mot diem)"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.sync_success.name}\""
                    aggregation = {
                      alignmentPeriod  = "300s"
                      perSeriesAligner = "ALIGN_SUM"
                    }
                  }
                }
                plotType = "STACKED_BAR"
              }]
              # Khoang trong tren bieu do nay chinh la do tre dong bo.
              yAxis = { label = "lan", scale = "LINEAR" }
            }
          }
        },
        {
          xPos = 6, width = 6, height = 4
          widget = {
            title = "Job chay xong theo ket qua"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = join(" AND ", [
                      "resource.type=\"cloud_run_job\"",
                      "metric.type=\"run.googleapis.com/job/completed_task_attempt_count\"",
                    ])
                    aggregation = {
                      alignmentPeriod    = "300s"
                      perSeriesAligner   = "ALIGN_SUM"
                      crossSeriesReducer = "REDUCE_SUM"
                      groupByFields      = ["resource.label.job_name", "metric.label.result"]
                    }
                  }
                }
                plotType = "LINE"
              }]
            }
          }
        },
        {
          yPos = 4, width = 6, height = 4
          widget = {
            title = "Do tre request cua API (p95)"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = join(" AND ", [
                      "resource.type=\"cloud_run_revision\"",
                      "metric.type=\"run.googleapis.com/request_latencies\"",
                      "resource.label.service_name=\"dataops-api\"",
                    ])
                    aggregation = {
                      alignmentPeriod  = "300s"
                      perSeriesAligner = "ALIGN_PERCENTILE_95"
                    }
                  }
                }
                plotType = "LINE"
              }]
              yAxis = { label = "ms", scale = "LINEAR" }
            }
          }
        },
        {
          xPos = 6, yPos = 4, width = 6, height = 4
          widget = {
            title = "Loi 5xx cua web va api"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = join(" AND ", [
                      "resource.type=\"cloud_run_revision\"",
                      "metric.type=\"run.googleapis.com/request_count\"",
                      "metric.label.response_code_class=\"5xx\"",
                    ])
                    aggregation = {
                      alignmentPeriod    = "300s"
                      perSeriesAligner   = "ALIGN_SUM"
                      crossSeriesReducer = "REDUCE_SUM"
                      groupByFields      = ["resource.label.service_name"]
                    }
                  }
                }
                plotType = "STACKED_BAR"
              }]
            }
          }
        },
      ]
    }
  })
}
