# VPC rieng cho ung dung. Custom mode — khong tu sinh subnet o moi region,
# chi tao dung cai minh can.

resource "google_compute_network" "vpc" {
  project                 = var.project_id
  name                    = "dataops-vpc"
  auto_create_subnetworks = false
  description             = "VPC cho Cloud Run <-> Cloud SQL qua private IP"
}

# Subnet nay phuc vu Direct VPC egress cua Cloud Run.
resource "google_compute_subnetwork" "main" {
  project       = var.project_id
  name          = "dataops-subnet"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.10.0.0/24"

  # Can thiet de xem duoc luu luong bi chan khi debug ket noi.
  private_ip_google_access = true
}

# --- Private Services Access: dai IP danh rieng cho Cloud SQL ---
# Google quan ly dai nay trong project cua ho va peer sang VPC cua minh.

resource "google_compute_global_address" "psa_range" {
  project       = var.project_id
  name          = "dataops-psa-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "psa" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.psa_range.name]

  # Cho phep terraform destroy go peering; khong co dong nay se ket o destroy.
  deletion_policy = "ABANDON"
}
