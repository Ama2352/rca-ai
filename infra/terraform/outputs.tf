output "aws_region" {
  value       = var.aws_region
  description = "Region for SSM and the EC2 instance."
}

output "instance_id" {
  value       = aws_instance.demo.id
  description = "Single deployment target used by GitHub Actions."
}

output "public_ip" {
  value       = aws_instance.demo.public_ip
  description = "Current public IPv4; update DuckDNS manually after it changes."
}

output "github_deploy_role_arn" {
  value       = aws_iam_role.github_deploy.arn
  description = "OIDC role assumed by the main-branch deployment job."
}
