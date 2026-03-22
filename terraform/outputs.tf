output "eks_cluster_name" {
  description = "EKS cluster name for kubectl configuration"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = module.eks.cluster_endpoint
}

output "ecr_repository_url" {
  description = "ECR repository URL for docker push"
  value       = aws_ecr_repository.api.repository_url
}

output "s3_bucket_name" {
  description = "S3 bucket for investment data"
  value       = aws_s3_bucket.data.id
}

output "api_pod_role_arn" {
  description = "IAM role ARN for Kubernetes service account annotation"
  value       = aws_iam_role.api_pod_role.arn
}

output "configure_kubectl" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${module.eks.cluster_name}"
}
