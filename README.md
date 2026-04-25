# Barbican UI

A production-grade web interface for managing OpenStack Barbican secrets, containers, orders, and consumers — built with Python/Flask.

![Python](https://img.shields.io/badge/python-3.12-blue)
![Flask](https://img.shields.io/badge/flask-3.x-green)
![License](https://img.shields.io/badge/license-MIT-blue)

## Motivation

Many virtual machine and Kubernetes cluster providers are built on top of OpenStack and expose its API — for example [OVHcloud](https://www.ovhcloud.com/). This means **Barbican, the built-in OpenStack secret manager, is already available** as part of the infrastructure — no additional setup required.

The primary goal of this project is to leverage Barbican as a **simple, zero-install secret engine** for projects running on such providers. Barbican can also be queried by tools like [External Secrets Operator](https://external-secrets.io/) on Kubernetes, giving you a complete secrets workflow — without deploying and maintaining a full [HashiCorp Vault](https://www.vaultproject.io/) instance.

**Why not just use [Horizon](https://docs.openstack.org/horizon/latest/) or [Skyline](https://docs.openstack.org/skyline/latest/)?** These are full-featured OpenStack dashboards — they're heavy, require broad admin-level API permissions, and are complex to deploy. Barbican UI is intentionally **lightweight and focused**: it only needs the Barbican `creator` role, talks to just two API endpoints (Keystone auth + Barbican), and can be deployed as a single container.

## Features

- **Full Barbican API coverage** — all 16 CLI-equivalent operations:
  - Secrets: store, list, get, delete, update
  - Containers: create, list, get, delete
  - Consumers: create, list, delete
  - Orders: create, list, get, delete
- **Virtual folders** — organize secrets hierarchically using `/` in names (e.g. `production/database/password`), with breadcrumb navigation, folder browsing, and path autocomplete
- **Three payload modes:**
  - **Simple** — plain text or binary
  - **Key-Value** — dynamic key-value pairs stored as JSON
  - **JSON** — graphical tree/code/form editor powered by JSONEditor (similar to HashiCorp Vault)
- **OpenStack Keystone authentication** — users log in with their own credentials; auto-detect project Name vs ID
- **Region-aware** — select OpenStack region at login; Barbican endpoint discovered per-region from service catalog
- **Minimal permissions** — requires only Barbican `creator` role, no admin access
- **In-app documentation** — Docs tab with detailed explanations of all Barbican concepts
- **Security hardened** — session IP binding, Secure cookies, CSP headers, X-Frame-Options, non-root container
- **Disk-based caching** — reduces API calls using `diskcache` with configurable TTL
- **No external database** — fully self-contained, all data from Barbican API
- **Production-ready** — Dockerfile, Helm chart, HPA, health probes, security headers

## Quick Start

### Local Development

```bash
# Clone and set up
git clone <repo-url> && cd barbican-ui
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure (copy and edit)
cp .env.example .env
# Edit .env with your Keystone URL, region, etc.

# Run
flask --app app:create_app run --port 8080 --debug
```

### Docker

```bash
docker build -t barbican-ui:latest .
docker run -p 8080:8080 --env-file .env barbican-ui:latest
```

### Docker Compose

```bash
cp .env.example .env   # edit with your values
docker-compose up -d
```

### Helm (Kubernetes)

```bash
helm install barbican-ui ./helm/barbican-ui \
  --set config.OS_AUTH_URL=https://keystone.example.com/v3 \
  --set config.OS_REGION_NAME=RegionOne \
  --set secrets.SECRET_KEY=$(openssl rand -hex 32)
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OS_AUTH_URL` | **Yes** | — | Keystone v3 endpoint (e.g. `https://keystone.example.com/v3`) |
| `OS_IDENTITY_API_VERSION` | No | `3` | Keystone API version |
| `OS_USER_DOMAIN_NAME` | No | `Default` | Default user domain for login form |
| `OS_PROJECT_DOMAIN_NAME` | No | `Default` | Default project domain for login form |
| `OS_REGION_NAME` | No | — | Default OpenStack region (user can override at login) |
| `OS_TENANT_NAME` | No | — | Default project/tenant name (pre-fills login form) |
| `OS_TENANT_ID` | No | — | Default project/tenant ID (alternative to name) |
| `BARBICAN_ENDPOINT_AUTODISCOVERY` | No | `true` | Discover Barbican endpoint from service catalog |
| `OS_BARBICAN_ENDPOINT` | Conditional | — | Explicit Barbican URL — always overrides autodiscovery. **Required** if autodiscovery is `false` |
| `SECRET_KEY` | **Yes** | `change-me` | Flask session signing key. **Must be identical across all replicas** |
| `SESSION_LIFETIME_SECONDS` | No | `3600` | Session/token validity in seconds |
| `SESSION_COOKIE_SECURE` | No | `true` | Send cookie only over HTTPS. Set to `false` for local HTTP dev |
| `SESSION_BIND_IP` | No | `true` | Bind session to client IP (stolen cookies won't work from other IPs) |
| `CACHE_TTL_SECONDS` | No | `300` | Disk cache TTL in seconds |
| `CACHE_DIR` | No | `/tmp/barbican-ui-cache` | Cache directory path |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `FLASK_PORT` | No | `8080` | HTTP listen port |

## Virtual Folders

Barbican has no native folder support. This UI adds virtual folders by parsing `/` in secret names:

```
production/database/mysql-password    →  📁 production / 📁 database / 🔑 mysql-password
production/api/stripe-key             →  📁 production / 📁 api / 🔑 stripe-key
staging/database/mysql-password       →  📁 staging / 📁 database / 🔑 mysql-password
```

- **Breadcrumb navigation** at the top of the secrets list
- **Folder buttons** with item counts
- **Path field** when creating secrets, with autocomplete of existing paths
- **Search** works across all folders

## Security

| Feature | Description |
|---------|-------------|
| `HttpOnly` cookies | JavaScript cannot read the session cookie |
| `Secure` cookies | Cookie transmitted only over HTTPS (production) |
| `SameSite=Lax` | CSRF protection |
| Session IP binding | Session rejected if client IP changes |
| Content-Security-Policy | Restricts script/style sources to self + CDN |
| X-Frame-Options: DENY | Prevents clickjacking via iframe embedding |
| X-Content-Type-Options | Prevents MIME type sniffing |
| Non-root container | Dockerfile runs as unprivileged user |

## Required OpenStack Permissions

See [docs/permissions.md](docs/permissions.md) for full details.

**TL;DR:** Only **two** OpenStack API endpoints are used:

1. `POST /v3/auth/tokens` on Keystone — any valid user
2. Barbican API (`/v1/secrets`, `/v1/containers`, `/v1/orders`) — project-scoped `creator` role

**No admin access needed. No access to Nova, Neutron, Glance, or any other service.**

## Running Tests

```bash
pip install -r requirements.txt
pytest
```

40 tests (unit + integration), ~80% code coverage. Report generated in `htmlcov/`.

## Documentation

- [Architecture](docs/architecture.md) — components, caching strategy, request flow, deployment diagram
- [Permissions](docs/permissions.md) — detailed breakdown of every API endpoint and required role
- [Deployment](docs/deployment.md) — Docker, Compose, Helm with production checklist
- [API Coverage](docs/api-coverage.md) — mapping of all 16 CLI commands to UI locations
- **In-app Docs tab** — accessible after login, explains all Barbican concepts

## License

MIT
