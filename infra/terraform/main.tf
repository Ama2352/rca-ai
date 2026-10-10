locals {
  secret_parameter_arns = [
    for name in ["GROQ_API_KEY", "CEREBRAS_API_KEY"] :
    "arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}:${var.aws_account_id}:parameter/rca-ai/demo/prod/${name}"
  ]

  config_env_b64 = base64encode(join("\n", [
    "AWS_REGION=${var.aws_region}",
    "RCA_DEMO_HOST=${var.demo_hostname}",
    "RCA_PROXY_SUBNET=${var.proxy_subnet_cidr}",
    "RCA_CONFIG_DIR=/etc/rca-demo",
    "RCA_CONFIG_FILE=/etc/rca-demo/config.env",
    "RCA_SECRET_DIR=/etc/rca-demo/secrets",
    "RCA_COMPOSE_FILE=/etc/rca-demo/compose.prod.yaml",
    "DOCKERHUB_FRONTEND_REPOSITORY=${var.dockerhub_frontend_repository}",
    "DOCKERHUB_BACKEND_REPOSITORY=${var.dockerhub_backend_repository}",
    ""
  ]))
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnet" "selected" {
  id = var.public_subnet_id
}

data "aws_ami" "ubuntu" {
  owners      = ["099720109477"]
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-*"]
  }
  filter {
    name   = "architecture"
    values = [var.architecture == "amd64" ? "x86_64" : "arm64"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
}

resource "aws_security_group" "demo" {
  name        = "rca-demo-public"
  description = "Caddy HTTPS ingress only; no SSH or backend port."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP redirect and ACME"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS application"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "demo" {
  ami                                  = data.aws_ami.ubuntu.id
  instance_type                        = var.instance_type
  subnet_id                            = data.aws_subnet.selected.id
  vpc_security_group_ids               = [aws_security_group.demo.id]
  iam_instance_profile                 = aws_iam_instance_profile.demo.name
  associate_public_ip_address          = true
  instance_initiated_shutdown_behavior = "stop"
  user_data_replace_on_change          = false
  user_data_base64 = base64gzip(templatefile("${path.module}/cloud-init.yaml.tftpl", {
    config_env_b64          = local.config_env_b64
    compose_file_b64        = filebase64("${path.module}/../../compose.prod.yaml")
    deploy_script_b64       = filebase64("${path.module}/../../deploy/scripts/deploy.sh")
    fetch_secrets_script_b64 = filebase64("${path.module}/../../deploy/scripts/fetch-secrets.sh")
  }))

  root_block_device {
    encrypted             = true
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gib
    delete_on_termination = true
  }
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  lifecycle {
    precondition {
      condition     = data.aws_subnet.selected.vpc_id == data.aws_vpc.default.id
      error_message = "Choose a public subnet in the account's default VPC."
    }
  }

  tags = { Name = "rca-demo" }
}
