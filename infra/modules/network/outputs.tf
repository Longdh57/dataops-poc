output "network_id" {
  value = google_compute_network.vpc.id
}

output "network_self_link" {
  value = google_compute_network.vpc.self_link
}

output "subnet_id" {
  value = google_compute_subnetwork.main.id
}

output "psa_connection" {
  description = "Cloud SQL phai depends_on cai nay, neu khong se tao truoc khi co peering"
  value       = google_service_networking_connection.psa.id
}
