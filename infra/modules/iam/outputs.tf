output "deployer_email" {
  value = local.ci_enabled ? google_service_account.deployer[0].email : null
}

output "workload_identity_provider" {
  description = "Dan vao GitHub Actions o buoc google-github-actions/auth"
  value       = local.ci_enabled ? google_iam_workload_identity_pool_provider.github[0].name : null
}
