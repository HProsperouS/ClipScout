variable "aws_region" {
  description = "AWS region (e.g. ap-southeast-1 for Singapore)"
  type        = string
  default     = "ap-southeast-1"
}

variable "architecture" {
  description = "AMI architecture: arm64 (Graviton, matches Apple Silicon Docker image) or x86_64"
  type        = string
  default     = "arm64"
}

variable "instance_type" {
  description = "EC2 instance type. For ARM Free Tier use t4g.micro; for x86 use t3.micro."
  type        = string
  default     = "t4g.micro"
}

variable "key_name" {
  description = "Name of an existing EC2 key pair for SSH (create in AWS Console or CLI)"
  type        = string
}

variable "app_port" {
  description = "Port the ClipScout container listens on"
  type        = number
  default     = 8000
}
