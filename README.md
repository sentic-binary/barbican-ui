# Barbican UI

A production-grade web interface for managing OpenStack Barbican secrets, containers, orders, and consumers — built with Python/Flask.

![Python](https://img.shields.io/badge/python-3.12-blue)
![Flask](https://img.shields.io/badge/flask-3.x-green)
![License](https://img.shields.io/badge/license-MIT-blue)

## Features

- **Full Barbican API coverage** — all 15 CLI-equivalent operations:
  - Secrets: store, list, get, delete, update
  - Containers: create, list, get, delete
  - Consumers: create, list, delete
  - Orders: create, list, get, delete
- **Key-Value secret editor** — add/remove key-value pairs stored as JSON
- **JSON editor** — graphical tree/code/form views powered by JSONEditor (similar to HashiCorp Vault)
- **OpenStack Keystone authentication** — users log in with their own credentials
- **Minimal permissions** — requires only Barbican `creator` role, no admin access
- **Disk-based caching** — reduces API calls using `diskcache` with configurable TTL
- **No external database** — fully self-contained, all data from Barbican API
- **Production-ready** — Dockerfile, Helm chart, HPA, health probes, non-root container

## Quick Start

### Local Development

```bash
# Clone and set up
git clone <repo-url> && cd barbican-ui
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure (copy and edit)
cp .env.example .env
# Edit .env with your Keystone URL, etc.

# Run
flask --app app:create_app run --port 8080 --debug
```

### Docker

```bash
# Build
docker build -t barbican-ui:latest .

# Run
docker run -p 8080:8080 --env-file .env barbican-ui:latest
```

### Docker Compose

```bash
cp .env.example .env   # edit with your values
docker-compose up -d
```

### Helm (Kubernetes)

```bash
# Install
helm install barbican-ui ./helm/barbican-ui \
  --set config.OS_AUTH_URL=https://keystone.example.com/v3 \
  --set secrets.SECRET_KEY=$(openssl rand -hex 32)

# With ingress
helm install barbican-ui ./helm/barbican-ui \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=barbican.example.com \
  --set ingress.hosts[0].paths[0].path=/ \
  --set ingress.hosts[0].paths[0].pathType=Prefix
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OS_AUTH_URL` | **Yes** | — | Keystone v3 endpoint (e.g. `https://keystone.example.com/v3`) |
| `OS_IDENTITY_API_VERSION` | No | `3` | Keystone API version |
| `OS_USER_DOMAIN_NAME` | No | `Default` | Default user domain for login form |
| `OS_PROJECT_DOMAIN_NAME` | No | `Default` | Default project domain for login form |
| `OS_REGION_NAME` | No | — | OpenStack region (for endpoint discovery) |
| `OS_TENANT_NAME` | No | — | Default project name (pre-fills login form) |
| `OS_TENANT_ID` | No | — | Default project ID (alternative to name) |
| `BARBICAN_ENDPOINT_AUTODISCOVERY` | No | `true` | Discover Barbican from service catalog |
| `OS_BARBICAN_ENDPOINT` | Conditional | — | Explicit Barbican URL (always overrides discovery). **Required** if autodiscovery is `false` |
| `SECRET_KEY` | **Yes** | `change-me` | Flask session signing key. **Must be identical across all replicas** |
| `SESSION_LIFETIME_SECONDS` | No | `3600` | Session/token validity in seconds |
| `CACHE_TTL_SECONDS` | No | `300` | Disk cache TTL in seconds |
| `CACHE_DIR` | No | `/tmp/barbican-ui-cache` | Cache directory path |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `FLASK_PORT` | No | `8080` | HTTP listen port |

## Required OpenStack Permissions

See [docs/permissions.md](docs/permissions.md) for full details.

**TL;DR:** This application uses only **two** OpenStack API endpoints:

1. `POST /v3/auth/tokens` on Keystone — any valid user can call this
2. Barbican API (`/v1/secrets`, `/v1/containers`, `/v1/orders`) — requires project-scoped `creator` role

**No admin, service, or other elevated permissions are needed.**

## Running Tests

```bash
pip install -r requirements.txt
pytest
```

Coverage report is generated in `htmlcov/`.

## Architecture

See [docs/architecture.md](docs/architecture.md).

## License

MIT
