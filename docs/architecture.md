# Architecture

## Overview

Barbican UI is a stateless Python/Flask web application that acts as a browser-based proxy to the OpenStack Barbican API. It authenticates users via Keystone and manages secrets, containers, orders, and consumers through Barbican's REST API.

```
┌──────────────┐     ┌────────────────────┐     ┌────────────────┐
│              │     │                    │     │    Keystone    │
│   Browser    │────▶│    Barbican UI     │────▶│  POST /v3/     │
│              │◀────│  (Flask/Gunicorn)  │     │  auth/tokens   │
│              │     │                    │     └────────────────┘
│              │     │   ┌────────────┐   │
│              │     │   │  diskcache │   │     ┌────────────────┐
│              │     │   └────────────┘   │     │    Barbican    │
│              │     │                    │────▶│  /v1/secrets   │
│              │     │                    │◀────│  /v1/containers│
└──────────────┘     └────────────────────┘     │  /v1/orders    │
                                                └────────────────┘
```

## Components

### 1. Flask Application (`app/`)

- **`__init__.py`** — Application factory (`create_app()`)
- **`config.py`** — Environment variable configuration with validation
- **`auth.py`** — Keystone v3 password authentication (single endpoint: `POST /v3/auth/tokens`)
- **`barbican.py`** — Barbican API client covering all 15 operations
- **`cache.py`** — Disk-based cache using `diskcache` library

### 2. Routes (`app/routes/`)

- **`auth_routes.py`** — Login, logout, index redirect
- **`secrets.py`** — Secret CRUD + update payload
- **`containers.py`** — Container CRUD
- **`consumers.py`** — Consumer create/delete (nested under containers)
- **`orders.py`** — Order CRUD
- **`health.py`** — `/healthz` and `/readyz` for Kubernetes probes

### 3. Templates (`app/templates/`)

Jinja2 templates using Bootstrap 5 (CDN) and JSONEditor (CDN):
- `base.html` — Layout with navbar, flash messages, footer
- `login.html` — Credential form with pre-filled defaults from env
- `secrets/` — list, create (3 modes: simple/KV/JSON), detail with reveal toggle
- `containers/` — list, create (with secret selection), detail (with consumers)
- `orders/` — list, create, detail

### 4. Caching Strategy

- **Library:** `diskcache` — SQLite-backed key-value store on local filesystem
- **TTL:** Configurable via `CACHE_TTL_SECONDS` (default 300s)
- **Cache keys:** `{project_id}:{resource_type}:{params}`
- **Invalidation:** Mutating operations (create/update/delete) invalidate related cache entries by prefix
- **Multi-replica:** Each pod has its own independent cache (no shared state). Losing cache only means extra API calls, never data loss.

### 5. Session Management

- Keystone tokens stored in Flask signed cookies (`SECRET_KEY`)
- Token expiry checked on every request via `@login_required` decorator
- All replicas must share the same `SECRET_KEY` for sessions to work cross-pod

## Request Flow

1. **User opens browser** → hits Flask route
2. **`@login_required`** checks session for valid (non-expired) token
3. If no token → redirect to `/login`
4. **Login** → Flask sends `POST /v3/auth/tokens` to Keystone → receives scoped token + service catalog
5. Token + Barbican endpoint stored in signed session cookie
6. **Authenticated request** → route handler calls `barbican.py` function → checks disk cache → if miss, calls Barbican API with user's token → caches response → renders template
7. **Mutating operations** → call Barbican API → invalidate related cache entries → redirect

## Deployment

```
┌───────────────────────────────────────────────┐
│               Kubernetes Cluster              │
│                                               │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  │
│  │   Pod 1   │  │   Pod 2   │  │   Pod N   │  │
│  │ gunicorn  │  │ gunicorn  │  │ gunicorn  │  │
│  │ 4 workers │  │ 4 workers │  │ 4 workers │  │
│  │ diskcache │  │ diskcache │  │ diskcache │  │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  │
│        │              │              │        │
│  ┌─────▼──────────────▼──────────────▼──────┐ │
│  │           Service (ClusterIP)            │ │
│  └────────────────────┬─────────────────────┘ │
│                       │                       │
│  ┌────────────────────▼─────────────────────┐ │
│  │        Ingress (optional, nginx)         │ │
│  └──────────────────────────────────────────┘ │
│                                               │
│  ConfigMap: non-sensitive env vars            │
│  Secret: SECRET_KEY                           │
│  HPA: 2–10 replicas, 70% CPU target           │
└───────────────────────────────────────────────┘
```

