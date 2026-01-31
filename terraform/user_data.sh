#!/bin/bash
set -e
# Install Docker 
yum update -y
yum install -y docker
systemctl enable docker
systemctl start docker
usermod -aG docker ec2-user
# App runs via: docker run -p ${app_port}:${app_port} <your-image>
# After SSH: docker run -d -p ${app_port}:${app_port} clipscout
# See README: push image to ECR or build on instance after SSH
