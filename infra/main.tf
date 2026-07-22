terraform {
  required_providers {
    aws   = { source = "hashicorp/aws",   version = "~> 5.0" }
    tls   = { source = "hashicorp/tls",   version = "~> 4.0" }
    local = { source = "hashicorp/local", version = "~> 2.0" }
    http  = { source = "hashicorp/http",  version = "~> 3.0" }
  }
}

provider "aws" {
  # uses whatever's already configured via `aws configure` / env vars
  # region must be set via AWS_DEFAULT_REGION env var or `aws configure`
}

# ── Data Sources ──

data "aws_vpc" "default" {
  default = true
}

data "aws_ami" "ubuntu_2404" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "http" "my_ip" {
  url = "https://api.ipify.org"
}

# ── SSH Key Pair (generated locally, never committed) ──

resource "tls_private_key" "deploy_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "local_file" "private_key_pem" {
  content         = tls_private_key.deploy_key.private_key_pem
  filename        = "${path.module}/llmgov-deploy.pem"
  file_permission = "0400"
}

resource "aws_key_pair" "deploy" {
  key_name   = "llmgov-deploy"
  public_key = tls_private_key.deploy_key.public_key_openssh
}

# ── Security Group ──
# Only SSH (restricted to deployer IP), gateway (8000), and Grafana (3000)
# are publicly reachable. Redis, ClickHouse, Ollama stay internal.

resource "aws_security_group" "deploy" {
  name        = "llmgov-deploy-sg"
  description = "LLMGov deployment - SSH restricted, gateway + Grafana public"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH from my IP only"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["${chomp(data.http.my_ip.response_body)}/32"]
  }
  ingress {
    description = "Gateway"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "Grafana"
    from_port   = 3000
    to_port     = 3000
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

# ── EC2 Instance ──

resource "aws_instance" "llmgov" {
  ami                         = data.aws_ami.ubuntu_2404.id
  instance_type               = "t3.large"
  key_name                    = aws_key_pair.deploy.key_name
  vpc_security_group_ids      = [aws_security_group.deploy.id]
  associate_public_ip_address = true

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  tags = { Name = "llmgov-deploy" }
}

output "public_ip" {
  value = aws_instance.llmgov.public_ip
}
