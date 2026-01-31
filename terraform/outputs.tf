output "public_ip" {
  description = "Public IP of the ClipScout EC2 instance"
  value       = aws_instance.clipscout.public_ip
}

output "app_url" {
  description = "URL to open ClipScout in the browser"
  value       = "http://${aws_instance.clipscout.public_ip}:8000"
}

output "ssh_command" {
  description = "Example SSH command (replace with your key path and key name)"
  value       = "ssh -i ~/.ssh/your-key.pem ec2-user@${aws_instance.clipscout.public_ip}"
}
