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

  secret_accessors = [var.api_service_account]
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
  api_service_account = var.api_service_account
  web_service_account = var.web_service_account
  iap_enabled         = var.iap_enabled
  public_access       = var.public_access
  api_image           = var.api_image
  web_image           = var.web_image
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
