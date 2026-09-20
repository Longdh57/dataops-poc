terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # State nam tren GCS, co versioning — hong thi roll back duoc.
  backend "gcs" {
    bucket = "dataops-poc-2026-tfstate"
    prefix = "poc"
  }
}
