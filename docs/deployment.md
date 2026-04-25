# Deployment Guide

## Prerequisites

- Python 3.12+ (for local development)
- Docker (for containerized deployment)
- Helm 3+ and Kubernetes 1.24+ (for k8s deployment)
- Access to an OpenStack cloud with Barbican service

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your values
flask --app app:create_app run --port 8080 --debug
```

## Docker

### Build

```bash
docker build -t barbican-ui:1.0.0 .
```

### Run

```bash
docker run -d \
  --name barbican-ui \
  -p 8080:8080 \
  -e OS_AUTH_URL=https://keystone.example.com/v3 \
  -e SECRET_KEY=$(openssl rand -hex 32) \
  -e BARBICAN_ENDPOINT_AUTODISCOVERY=true \
  barbican-ui:1.0.0
```

### Docker Compose

```bash
cp .env.example .env
# Edit .env
docker-compose up -d
```

## Kubernetes with Helm

### 1. Prepare the secret key

All replicas **must** share the same `SECRET_KEY` for session cookies to work across pods:

```bash
export BARBICAN_UI_SECRET_KEY=$(openssl rand -hex 32)
```

### 2. Install

```bash
helm install barbican-ui ./helm/barbican-ui \
  --namespace barbican-ui --create-namespace \
  --set config.OS_AUTH_URL=https://keystone.example.com/v3 \
  --set config.OS_REGION_NAME=RegionOne \
  --set secrets.SECRET_KEY=$BARBICAN_UI_SECRET_KEY
```

### 3. Enable Ingress

```bash
helm upgrade barbican-ui ./helm/barbican-ui \
  --namespace barbican-ui \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=barbican-ui.example.com \
  --set ingress.hosts[0].paths[0].path=/ \
  --set ingress.hosts[0].paths[0].pathType=Prefix \
  --set ingress.tls[0].secretName=barbican-ui-tls \
  --set ingress.tls[0].hosts[0]=barbican-ui.example.com
```

### 4. Enable Cache Persistence (Optional)

```bash
helm upgrade barbican-ui ./helm/barbican-ui \
  --namespace barbican-ui \
  --set persistence.enabled=true \
  --set persistence.size=2Gi
```

### 5. Custom Values File

Create `my-values.yaml`:

```yaml
config:
  OS_AUTH_URL: "https://keystone.example.com/v3"
  OS_REGION_NAME: "RegionOne"
  OS_TENANT_NAME: "my-project"
  CACHE_TTL_SECONDS: "600"

secrets:
  SECRET_KEY: "your-random-secret-key-here"

ingress:
  enabled: true
  hosts:
    - host: barbican.mycompany.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: barbican-tls
      hosts:
        - barbican.mycompany.com

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 20
```

```bash
helm install barbican-ui ./helm/barbican-ui -f my-values.yaml -n barbican-ui
```

## Production Checklist

- [ ] Set a strong random `SECRET_KEY` (at least 32 characters)
- [ ] Enable TLS via Ingress with cert-manager
- [ ] Set appropriate resource limits
- [ ] Configure HPA for your expected load
- [ ] Assign Barbican `creator` role to your OpenStack users
- [ ] Set `LOG_LEVEL=WARNING` in production
- [ ] Use Kubernetes Secrets or external secret managers for `SECRET_KEY`
- [ ] Monitor `/healthz` and `/readyz` endpoints
- [ ] Set `OS_CACERT` if your cloud uses internal/private PKI certificates

