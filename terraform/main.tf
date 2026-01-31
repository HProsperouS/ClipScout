terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Latest Amazon Linux 2 AMI (Free Tier eligible)
# Use arm64 for Graviton (t4g) so you can run the same image built on Apple Silicon Mac
data "aws_ami" "amazon_linux_2" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*-${var.architecture}-gp2"]
  }
}

# Security group: SSH + app port (no ALB)
resource "aws_security_group" "clipscout" {
  name        = "clipscout-sg"
  description = "ClipScout EC2: SSH and app port"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "ClipScout app"
    from_port   = var.app_port
    to_port     = var.app_port
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

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# EC2 instance (Free Tier: t4g.micro for ARM, t3.micro for x86)
resource "aws_instance" "clipscout" {
  ami                    = data.aws_ami.amazon_linux_2.id
  instance_type          = var.instance_type
  key_name               = var.key_name
  vpc_security_group_ids = [aws_security_group.clipscout.id]
  subnet_id              = tolist(data.aws_subnets.default.ids)[0]
  user_data              = templatefile("${path.module}/user_data.sh", { app_port = var.app_port })

  root_block_device {
    volume_size = 30 # Free Tier: 30 GB EBS
  }

  tags = {
    Name = "clipscout"
  }
}
