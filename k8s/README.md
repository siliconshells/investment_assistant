# Kubernetes Manifests

Uses [Kustomize](https://kustomize.io/) (built into `kubectl`) to manage
environment-specific configuration without template variables in YAML.

## Structure

```
k8s/
├── base/                    # Shared manifests, valid YAML, no variables
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── serviceaccount.yaml
│   ├── configmap.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   └── secrets.template.yaml   # NOT auto-applied, see below
└── overlays/
    ├── dev/                 # Local development: 1 replica, debug logging
    │   └── kustomization.yaml
    └── prod/                # AWS EKS: ECR image, IRSA, ALB ingress
        ├── kustomization.yaml
        └── ingress.yaml
```

## Usage

### Local / Dev

```bash
# Create secrets first
kubectl create namespace investment
kubectl create secret generic investment-api-secrets \
  --namespace=investment \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-... \
  --from-literal=OPENAI_API_KEY=sk-... \
  --from-literal=ALPHA_VANTAGE_API_KEY=...

# Preview what will be applied
kubectl kustomize k8s/overlays/dev

# Apply
kubectl apply -k k8s/overlays/dev
```

### Production (EKS)

```bash
# 1. Set the real ECR image (CI does this automatically)
cd k8s/overlays/prod
kustomize edit set image \
  investment-api=123456789.dkr.ecr.us-east-1.amazonaws.com/investment-assistant-api:abc123

# 2. Update the IRSA role ARN in kustomization.yaml
#    (or let CI inject it from Terraform output)

# 3. Create secrets from AWS Secrets Manager or CI variables
kubectl create secret generic investment-api-secrets ...

# 4. Apply
kubectl apply -k k8s/overlays/prod
```

### Validate without a cluster

```bash
# Kustomize renders locally, no cluster auth needed
kubectl kustomize k8s/overlays/dev
kubectl kustomize k8s/overlays/prod
```
