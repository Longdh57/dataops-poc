provider "google" {
  project = var.project_id
  region  = var.region
}

# Doc lai project de xac nhan credential va quyen truoc khi apply bat cu thu gi.
data "google_project" "this" {
  project_id = var.project_id
}

locals {
  labels = {
    app = "dataops"
    env = var.env
  }

  # Service account: uu tien gia tri trong tfvars (du an dang chay, tao tay
  # tu truoc), khong co thi dung tai khoan Terraform tu tao. Nho vay mot
  # project trong chi can terraform apply, con project dang chay khong bi
  # doi danh tinh duoi chan.
  sa = {
    api  = var.api_service_account != "" ? var.api_service_account : module.iam.service_accounts["api"]
    web  = var.web_service_account != "" ? var.web_service_account : module.iam.service_accounts["web"]
    jobs = var.jobs_service_account != "" ? var.jobs_service_account : module.iam.service_accounts["jobs"]
  }
}

module "network" {
  source     = "./modules/network"
  project_id = var.project_id
  region     = var.region
  labels     = local.labels
}

module "database" {
  source     = "./modules/database"
  project_id = var.project_id
  region     = var.region
  labels     = local.labels

  network_id     = module.network.network_id
  psa_connection = module.network.psa_connection

  secret_accessors = [local.sa.api, local.sa.jobs]
}

module "runtime" {
  source     = "./modules/runtime"
  project_id = var.project_id
  region     = var.region
  labels     = local.labels

  project_number      = data.google_project.this.number
  network_id          = module.network.network_id
  subnet_id           = module.network.subnet_id
  db_url_secret_id    = module.database.db_url_secret_id
  secret_iam_ready    = module.database.secret_iam_ready
  api_service_account = local.sa.api
  web_service_account = local.sa.web
  iap_enabled         = var.iap_enabled
  public_access       = var.public_access
  api_image           = var.api_image
  web_image           = var.web_image

  jobs_service_account = local.sa.jobs
  jobs_image           = var.jobs_image
  owner_email          = var.owner_email
  staging_bucket       = module.storage.bucket
  bq_dataset           = var.bq_dataset
  bq_analytics_dataset = module.data.analytics_dataset_id
}

module "iam" {
  source     = "./modules/iam"
  project_id = var.project_id
  region     = var.region
  labels     = local.labels

  project_number = data.google_project.this.number
  github_repo    = var.github_repo
  iap_members    = var.iap_members
}

module "data" {
  source     = "./modules/data"
  project_id = var.project_id
  region     = var.region
  labels     = local.labels

  dataset_id        = var.bq_dataset
  readers           = [local.sa.api, local.sa.jobs]
  analytics_writers = [local.sa.jobs]
}

module "storage" {
  source     = "./modules/storage"
  project_id = var.project_id
  region     = var.region
  labels     = local.labels

  writers = [local.sa.jobs]
  readers = [local.sa.api]
}

module "monitoring" {
  source          = "./modules/monitoring"
  project_id      = var.project_id
  alert_email     = var.alert_email
  sync_job_name   = module.runtime.sync_job
  qc_job_name     = module.runtime.qc_job
  export_job_name = module.runtime.export_job
  web_url         = var.web_domain != "" ? "https://${var.web_domain}" : module.runtime.web_url
}
