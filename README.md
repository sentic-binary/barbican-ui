# Barbican UI

A production-grade web interface for managing OpenStack Barbican secrets, containers, orders, and consumers — built with Python/Flask.

![Python](https://img.shields.io/badge/python-3.12-blue)
![Flask](https://img.shields.io/badge/flask-3.x-green)
![License](https://img.shields.io/badge/license-MIT-blue)

## Motivation

Many virtual machine and Kubernetes cluster providers are built on top of OpenStack and expose its API — for example [OVHcloud](https://www.ovhcloud.com/). This means **Barbican, the built-in OpenStack secret manager, is already available** as part of the infrastructure — no additional setup required.

The primary goal of this project is to leverage Barbican as a **simple, zero-install secret engine** for projects running on such providers. Barbican can also be queried by tools like [External Secrets Operator](https://external-secrets.io/) on Kubernetes, giving you a complete secrets workflow — without deploying and maintaining a full [HashiCorp Vault](https://www.vaultproject.io/) instance.

**Why not just use [Horizon](https://docs.openstack.org/horizon/latest/) or [Skyline](https://wiki.openstack.org/wiki/Skyline)?** These are full-featured OpenStack dashboards — they're heavy, require broad admin-level API permissions, and are complex to deploy. Barbican UI is intentionally **lightweight and focused**: it only needs the Barbican `creator` role, talks to just two API endpoints (Keystone auth + Barbican), and can be deployed as a single container.

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
# From GHCR (recommended)
docker run -p 8080:8080 --env-file .env ghcr.io/sentic-binary/barbican-ui:latest

# Or build locally
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
# Install from GHCR OCI registry
helm install barbican-ui oci://ghcr.io/sentic-binary/charts/barbican-ui \
  --version 1.0.0 \
  --set config.OS_AUTH_URL=https://keystone.example.com/v3 \
  --set config.OS_REGION_NAME=RegionOne \
  --set secrets.SECRET_KEY=$(openssl rand -hex 32)

# Or from local checkout
helm install barbican-ui ./helm/barbican-ui \
  --set image.tag=1.0.0 \
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
| `OS_CACERT` | No | — | Path to a CA certificate bundle for TLS verification. If unset, the system default CA bundle is used |
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

## Export / Import (Transfer)

Migrate secrets and containers between Barbican instances, regions, or projects.

**Export** downloads all resources as a versioned JSON file:
- Secrets with metadata and (optionally) plaintext payloads
- Containers with secret references resolved by name
- Consumers registered on containers

**Import** recreates resources from a previously exported file:
- **Skip existing** — skips secrets that already exist (matched by name)
- **Dry run** — preview what would be imported without creating anything
- Secrets are created first, then containers reference them by name → new ID
- Consumers are re-registered on the newly created containers

```
Instance A (region WAW)          Instance B (region GRA)
┌──────────────┐   JSON file   ┌──────────────┐
│  Secrets     │──── Export ──▶│              │
│  Containers  │               │  Import ───▶ │ Secrets
│  Consumers   │               │              │ Containers
└──────────────┘               └──────────────┘
```

> ⚠️ **Security:** Exported files contain plaintext secret values. Handle them with the same care as the secrets themselves.

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
pip install -r requirements-dev.txt
pytest
```

190+ tests (unit + integration), ~97% code coverage. Report generated in `htmlcov/`.

## Documentation

- [Architecture](docs/architecture.md) — components, caching strategy, request flow, deployment diagram
- [Permissions](docs/permissions.md) — detailed breakdown of every API endpoint and required role
- [Deployment](docs/deployment.md) — Docker, Compose, Helm with production checklist
- [API Coverage](docs/api-coverage.md) — mapping of all 16 CLI commands to UI locations
- **In-app Docs tab** — accessible after login, explains all Barbican concepts

## Releasing & Versioning

This project uses [Conventional Commits](https://www.conventionalcommits.org/) and [Release Please](https://github.com/googleapis/release-please) for fully automated releases.

### How it works

1. You write commits using conventional prefixes (see table below).
2. On every push to `main`, **Release Please** analyses new commits and opens (or updates) a PR titled _"chore: release vX.Y.Z"_ containing:
   - Updated `CHANGELOG.md`
   - Version bump in `version.txt`
3. When you **merge** that PR, Release Please creates a **git tag** `vX.Y.Z`.
4. The tag triggers the **Release workflow** which:
   - Runs tests (gate)
   - Builds & pushes a Docker image to `ghcr.io/sentic-binary/barbican-ui:X.Y.Z` + `:latest`
   - Packages & pushes the Helm chart to `oci://ghcr.io/sentic-binary/charts/barbican-ui:X.Y.Z`
   - Creates a GitHub Release with auto-generated notes

### Conventional Commits → version bumps

| Commit prefix | Version bump | Example |
|---|---|---|
| `fix:` | **patch** (0.0.X) | `fix: handle empty secret payload` |
| `feat:` | **minor** (0.X.0) | `feat: add secret rotation support` |
| `feat!:` or `BREAKING CHANGE:` in footer | **major** (X.0.0) | `feat!: remove v1 API compatibility` |
| `docs:`, `chore:`, `ci:`, `style:`, `refactor:`, `test:` | no release | `docs: update deployment guide` |

### Manual release (optional)

If you want to release without Release Please, create and push a tag manually:

```bash
git tag v1.2.3
git push origin v1.2.3
```

### Artifacts

| Artifact | Location |
|---|---|
| Docker image | `ghcr.io/sentic-binary/barbican-ui:<version>` |
| Docker image (latest) | `ghcr.io/sentic-binary/barbican-ui:latest` |
| Helm chart (OCI) | `oci://ghcr.io/sentic-binary/charts/barbican-ui` |
| GitHub Release | [Releases page](../../releases) |

## License

MIT

.