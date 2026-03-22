locals {
  name = var.project_name
}

data "aws_availability_zones" "available" {
  state = "available"
}

# =============================================================================
# VPC
# =============================================================================

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "${local.name}-vpc"
  cidr = "10.0.0.0/16"

  azs             = slice(data.aws_availability_zones.available.names, 0, 2)
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = true  # cost-saving for demo; use per-AZ in prod
  enable_dns_hostnames = true
  enable_dns_support   = true

  # Tags required for EKS auto-discovery — cluster name must be included
  public_subnet_tags = {
    "kubernetes.io/role/elb"                              = 1
    "kubernetes.io/cluster/${local.name}-eks"              = "shared"
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"                      = 1
    "kubernetes.io/cluster/${local.name}-eks"              = "shared"
  }
}

# =============================================================================
# EKS Cluster
# =============================================================================

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "${local.name}-eks"
  cluster_version = "1.30"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Nodes in private subnets need the private endpoint to reach the API
  # without going through NAT → public internet → back in.
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  # Use EKS API for auth (required for access_entries)
  authentication_mode = "API_AND_CONFIG_MAP"

  # Grant the Terraform caller admin access to the cluster
  enable_cluster_creator_admin_permissions = true

  # Grant the CI/CD deploy role access to the cluster
  access_entries = var.ci_deploy_role_arn != "" ? {
    ci_deploy = {
      principal_arn = var.ci_deploy_role_arn
      policy_associations = {
        cluster_admin = {
          policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = {
            type = "cluster"
          }
        }
      }
    }
  } : {}

  # Allow nodes and pods to talk to the control plane
  node_security_group_additional_rules = {
    ingress_self_all = {
      description = "Node-to-node communication"
      protocol    = "-1"
      from_port   = 0
      to_port     = 0
      type        = "ingress"
      self        = true
    }
    egress_all = {
      description = "Node outbound"
      protocol    = "-1"
      from_port   = 0
      to_port     = 0
      type        = "egress"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  eks_managed_node_groups = {
    default = {
      instance_types = [var.eks_node_instance_type]
      desired_size   = var.eks_desired_capacity
      min_size       = var.eks_min_size
      max_size       = var.eks_max_size
      subnet_ids     = module.vpc.private_subnets
    }
  }

  # Enable IRSA (IAM Roles for Service Accounts)
  enable_irsa = true
}

# =============================================================================
# VPC Endpoints — so nodes in private subnets can reach AWS APIs
# without depending solely on NAT gateway
# =============================================================================

# S3 gateway endpoint (free, needed for pulling ECR image layers)
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = module.vpc.vpc_id
  service_name = "com.amazonaws.${var.aws_region}.s3"

  route_table_ids = module.vpc.private_route_table_ids

  tags = { Name = "${local.name}-s3-endpoint" }
}

# Interface endpoints for ECR + STS (nodes need these to pull images and auth)
resource "aws_security_group" "vpc_endpoints" {
  name_prefix = "${local.name}-vpce-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }

  tags = { Name = "${local.name}-vpce-sg" }
}

resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.ecr.api"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${local.name}-ecr-api" }
}

resource "aws_vpc_endpoint" "ecr_dkr" {
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.ecr.dkr"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${local.name}-ecr-dkr" }
}

resource "aws_vpc_endpoint" "sts" {
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.sts"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${local.name}-sts" }
}

# =============================================================================
# S3 Bucket — structured investment data
# =============================================================================

resource "aws_s3_bucket" "data" {
  bucket = "${local.name}-data-${data.aws_caller_identity.current.account_id}"

  tags = {
    Purpose = "Structured stock price and analysis data"
  }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket = aws_s3_bucket.data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# =============================================================================
# ECR Repository — container images
# =============================================================================

resource "aws_ecr_repository" "api" {
  name                 = "${local.name}-api"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# =============================================================================
# IAM Role for Kubernetes Service Account (IRSA)
# =============================================================================

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "api_pod_role" {
  name = "${local.name}-api-pod-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = module.eks.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${module.eks.oidc_provider}:sub" = "system:serviceaccount:investment:investment-api-sa"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "api_s3_access" {
  name = "${local.name}-s3-access"
  role = aws_iam_role.api_pod_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
        ]
        Resource = [
          aws_s3_bucket.data.arn,
          "${aws_s3_bucket.data.arn}/*",
        ]
      }
    ]
  })
}
