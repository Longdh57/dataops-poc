output "deployer_email" {
  value = local.ci_enabled ? google_service_account.deployer[0].email : null
}

output "workload_identity_provider" {
  description = "Dan vao GitHub Actions o buoc google-github-actions/auth"
  value       = local.ci_enabled ? google_iam_workload_identity_pool_provider.github[0].name : null
}

output "service_accounts" {
  description = "Email cua ba service account chay ung dung"
  value       = { for k, sa in google_service_account.runtime : k => sa.email }
}
