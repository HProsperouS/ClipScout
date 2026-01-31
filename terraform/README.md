# ClipScout on EC2 (Terraform)

This Terraform setup provisions a single EC2 instance (Free Tier: t3.micro) with Docker installed. No ALB.

## Prerequisites

- [Terraform](https://www.terraform.io/downloads) >= 1.0
- AWS CLI configured (`aws configure`) or env vars `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- An **EC2 key pair** in AWS (for SSH). Create in Console: EC2 → Key Pairs → Create, download the `.pem` file.

## Usage

1. **Set your key pair name**

   Copy the example and edit:

   ```bash
   cp terraform.tfvars.example terraform.tfvars
   # Edit terraform.tfvars: set key_name = "your-actual-key-pair-name"
   ```

2. **Init and apply**

   ```bash
   cd terraform
   terraform init
   terraform plan
   terraform apply
   ```

3. **Outputs**

   After apply, Terraform prints:

   - `public_ip` – use for SSH and to open the app
   - `app_url` – e.g. `http://<public_ip>:8000`
   - `ssh_command` – example SSH command

4. **Deploy the app on the instance**

   SSH in and run the container. Two options:

   **Option A: Build and run on the instance**

   ```bash
   ssh -i ~/.ssh/your-key.pem ec2-user@<public_ip>
   sudo yum install -y git
   git clone <your-repo-url> clipscout && cd clipscout
   docker build -t clipscout .
   docker run -d -p 8000:8000 --name app clipscout
   ```

   **Option B: Push image to ECR, then pull and run on EC2**

   - Create an ECR repo (AWS Console or `aws ecr create-repository --repository-name clipscout`)
   - Build and push from your machine:  
     `docker build -t <account>.dkr.ecr.<region>.amazonaws.com/clipscout:latest .`  
     `docker push ...`
   - On EC2: attach an IAM role with `AmazonEC2ContainerRegistryReadOnly` (or run `aws ecr get-login-password` and `docker pull`), then `docker run -d -p 8000:8000 <image-uri>`.

5. **Open the app**

   In the browser: `http://<public_ip>:8000`.

## Variables

| Variable        | Description                    | Default     |
|----------------|--------------------------------|-------------|
| `aws_region`   | AWS region (Singapore: ap-southeast-1) | `ap-southeast-1` |
| `architecture` | `arm64` (Graviton, run Mac-built image) or `x86_64` | `arm64` |
| `instance_type`| EC2 type: `t4g.micro` (ARM Free Tier) or `t3.micro` (x86) | `t4g.micro` |
| `key_name`     | EC2 key pair name              | (required)  |
| `app_port`     | Container port                 | `8000`      |

## Destroy

```bash
terraform destroy
```
