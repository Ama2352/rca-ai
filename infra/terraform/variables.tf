variable "aws_region" {
  type        = string
  description = "AWS Region for EC2, SSM parameters, and the deployment role."
  validation {
    condition     = can(regex("^[a-z]{2}(-gov)?-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "Set a valid AWS Region."
  }
}

variable "aws_account_id" {
  type        = string
  description = "Expected 12-digit AWS account ID."
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must contain 12 digits."
  }
}

variable "architecture" {
  type        = string
  description = "Architecture measured by the offline container profile."
  validation {
    condition     = contains(["amd64", "arm64"], var.architecture)
    error_message = "architecture must be selected from profiling evidence."
  }
}

variable "instance_type" {
  type        = string
  description = "EC2 type selected from measured resource use."
}

variable "root_volume_size_gib" {
  type        = number
  description = "Encrypted gp3 size selected from measured image and host storage use."
  validation {
    condition     = var.root_volume_size_gib >= 8 && var.root_volume_size_gib <= 16384
    error_message = "Use a supported gp3 volume size."
  }
}

variable "public_subnet_id" {
  type        = string
  description = "Public subnet ID in the default VPC, with a route to an Internet Gateway."
}

variable "proxy_subnet_cidr" {
  type        = string
  description = "Dedicated Docker subnet trusted for Caddy-forwarded client IP headers."
  default     = "172.29.240.0/24"
  validation {
    condition     = can(cidrnetmask(var.proxy_subnet_cidr))
    error_message = "proxy_subnet_cidr must be a valid IPv4 CIDR."
  }
}

variable "github_repository" {
  type        = string
  description = "GitHub owner/repository allowed to assume the deployment role."
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "Use owner/repository form."
  }
}

variable "github_owner_id" {
  type = string
}

variable "github_repository_id" {
  type = string
}

variable "github_oidc_provider_ownership" {
  type        = string
  description = "Create the GitHub OIDC provider only when absent, otherwise reuse the existing ARN."
  validation {
    condition     = contains(["create", "external"], var.github_oidc_provider_ownership)
    error_message = "Use create or external OIDC provider ownership."
  }
}

variable "existing_github_oidc_provider_arn" {
  type        = string
  description = "Existing provider ARN when ownership is external."
  default     = ""
  validation {
    condition     = var.github_oidc_provider_ownership == "create" ? var.existing_github_oidc_provider_arn == "" : can(regex("^arn:[^:]+:iam::[0-9]{12}:oidc-provider/token\\.actions\\.githubusercontent\\.com$", var.existing_github_oidc_provider_arn))
    error_message = "External mode needs the existing GitHub OIDC provider ARN."
  }
}

variable "github_oidc_thumbprint" {
  type        = string
  description = "Optional OIDC thumbprint used only when Terraform creates the provider."
  default     = ""
  validation {
    condition = var.github_oidc_thumbprint == "" || (
      var.github_oidc_provider_ownership == "create" &&
      can(regex("^[0-9A-Fa-f]{40}$", var.github_oidc_thumbprint))
    )
    error_message = "Leave the thumbprint empty or provide exactly 40 hexadecimal characters in create mode."
  }
}

variable "dockerhub_frontend_repository" {
  type        = string
  description = "Public Docker Hub frontend namespace/repository."
  validation {
    condition     = can(regex("^[a-z0-9]+([._-][a-z0-9]+)*/[a-z0-9]+([._-][a-z0-9]+)*$", var.dockerhub_frontend_repository))
    error_message = "Use a lowercase Docker Hub namespace/repository."
  }
}

variable "dockerhub_backend_repository" {
  type        = string
  description = "Public Docker Hub backend namespace/repository."
  validation {
    condition     = can(regex("^[a-z0-9]+([._-][a-z0-9]+)*/[a-z0-9]+([._-][a-z0-9]+)*$", var.dockerhub_backend_repository))
    error_message = "Use a lowercase Docker Hub namespace/repository."
  }
}

variable "demo_hostname" {
  type        = string
  description = "DuckDNS hostname used by Caddy; its A record is updated manually."
  validation {
    condition     = can(regex("^[A-Za-z0-9-]+\\.duckdns\\.org$", var.demo_hostname))
    error_message = "Use a DuckDNS hostname without a scheme."
  }
}
