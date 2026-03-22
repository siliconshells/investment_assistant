# Terraform — AWS Infrastructure

Provisions all AWS resources needed to run the AI Investment Research Assistant.

## Resources Created

| Resource | Purpose |
|----------|---------|
| VPC + subnets | Isolated networking with public/private tiers |
| EKS cluster | Kubernetes control plane + managed node group |
| S3 bucket | Versioned, encrypted storage for price data |
| ECR repository | Container image registry with scan-on-push |
| IAM role (IRSA) | Least-privilege S3 access for API pods |

## Prerequisites

- AWS CLI configured (`aws configure`)
- Terraform >= 1.5
- Sufficient IAM permissions to create the above resources

## Usage

```bash
# Initialize providers and modules
terraform init

# Preview changes
terraform plan -out=plan.tfplan

# Apply
terraform apply plan.tfplan

# Configure kubectl to talk to the new cluster
$(terraform output -raw configure_kubectl)
```

## Cost Estimate (demo sizing)

With `t3.medium` × 2 nodes + single NAT gateway, expect roughly **$100–150/month**.
To minimize cost, scale `eks_desired_capacity` to 1 and destroy when not demoing.

## Teardown

```bash
terraform destroy
```

## Variables

Override via `terraform.tfvars` or `-var`:

```hcl
aws_region             = "us-west-2"
eks_node_instance_type = "t3.small"
eks_desired_capacity   = 1
```
