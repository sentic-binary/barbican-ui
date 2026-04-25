# Required OpenStack Permissions

## Overview

Barbican UI is designed to require the **absolute minimum** OpenStack permissions. It does **not** need admin access, service accounts, or access to any OpenStack service other than Keystone (for authentication) and Barbican (for secret management).

## Endpoints Used

### 1. Keystone Identity Service

| Method | Endpoint | Purpose | Permission Level |
|--------|----------|---------|-----------------|
| `POST` | `/v3/auth/tokens` | Authenticate user, obtain scoped token | **Any valid user** |

This is the **only** Keystone endpoint called. It is the standard authentication endpoint available to all OpenStack users. No token validation, user listing, project listing, or any other identity operation is performed.

The service catalog is extracted from the authentication response body (it is included automatically by Keystone when a scoped token is issued). This avoids the need to call `GET /v3/endpoints` or `GET /v3/services`, which may require elevated permissions.

### 2. Barbican Key Manager Service

| Method | Endpoint | Purpose | Permission Level |
|--------|----------|---------|-----------------|
| `POST` | `/v1/secrets` | Store a new secret | `creator` role |
| `GET` | `/v1/secrets` | List secrets | `observer` or `creator` role |
| `GET` | `/v1/secrets/{id}` | Get secret metadata | `observer` or `creator` role |
| `GET` | `/v1/secrets/{id}/payload` | Get secret payload | `observer` or `creator` role |
| `PUT` | `/v1/secrets/{id}` | Update secret payload | `creator` role |
| `DELETE` | `/v1/secrets/{id}` | Delete a secret | `creator` role |
| `POST` | `/v1/containers` | Create a container | `creator` role |
| `GET` | `/v1/containers` | List containers | `observer` or `creator` role |
| `GET` | `/v1/containers/{id}` | Get container details | `observer` or `creator` role |
| `DELETE` | `/v1/containers/{id}` | Delete a container | `creator` role |
| `POST` | `/v1/containers/{id}/consumers` | Register a consumer | `creator` role |
| `GET` | `/v1/containers/{id}/consumers` | List consumers | `observer` or `creator` role |
| `DELETE` | `/v1/containers/{id}/consumers` | Remove a consumer | `creator` role |
| `POST` | `/v1/orders` | Create an order | `creator` role |
| `GET` | `/v1/orders` | List orders | `observer` or `creator` role |
| `GET` | `/v1/orders/{id}` | Get order details | `observer` or `creator` role |
| `DELETE` | `/v1/orders/{id}` | Delete an order | `creator` role |

## Minimum Required Role

The **`creator`** role on the Barbican (key-manager) service is sufficient for all operations. This role includes read access (`observer` capabilities) plus write/delete operations.

### How to Assign the Role

```bash
# Find the creator role ID
openstack role list | grep creator

# Assign to a user on a project
openstack role add --project <project-id> --user <user-id> creator
```

If your OpenStack deployment uses a different role name for Barbican access, consult your cloud administrator.

## What This App Does NOT Need

- ❌ `admin` role on any service
- ❌ Access to Nova, Neutron, Glance, Cinder, or any other OpenStack service
- ❌ `GET /v3/endpoints` or `GET /v3/services` (catalog comes from auth response)
- ❌ `GET /v3/users` or `GET /v3/projects` (no user/project enumeration)
- ❌ Service account or application credentials (uses user's own password)

## Barbican Endpoint Discovery

The Barbican endpoint is resolved in this priority order:

1. **`OS_BARBICAN_ENDPOINT`** environment variable — always wins when set
2. **Service catalog autodiscovery** — extracted from Keystone auth response (`BARBICAN_ENDPOINT_AUTODISCOVERY=true`, the default)
3. If `BARBICAN_ENDPOINT_AUTODISCOVERY=false` and `OS_BARBICAN_ENDPOINT` is not set, the application will fail to start

This design means the app never makes a separate API call to discover endpoints.

