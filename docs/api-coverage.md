# API Coverage

This document maps every `openstack secret` CLI command to its corresponding Barbican UI feature and underlying API endpoint.

## Complete Command Coverage

| # | CLI Command | Barbican API | UI Location | Status |
|---|-------------|-------------|-------------|--------|
| 1 | `secret store` | `POST /v1/secrets` | Secrets → Create Secret (Simple / Key-Value / JSON mode) | ✅ |
| 2 | `secret list` | `GET /v1/secrets` | Secrets → List (with search & pagination) | ✅ |
| 3 | `secret get` | `GET /v1/secrets/{id}` + `GET /v1/secrets/{id}/payload` | Secrets → Detail (metadata + reveal payload) | ✅ |
| 4 | `secret delete` | `DELETE /v1/secrets/{id}` | Secrets → Detail → Delete button | ✅ |
| 5 | `secret update` | `PUT /v1/secrets/{id}` | Secrets → Detail → Set Payload form (Simple / KV / JSON) | ✅ |
| 6 | `secret container create` | `POST /v1/containers` | Containers → Create (select secrets to link) | ✅ |
| 7 | `secret container list` | `GET /v1/containers` | Containers → List (with pagination) | ✅ |
| 8 | `secret container get` | `GET /v1/containers/{id}` | Containers → Detail (metadata + linked secrets) | ✅ |
| 9 | `secret container delete` | `DELETE /v1/containers/{id}` | Containers → Detail → Delete button | ✅ |
| 10 | `secret consumer create` | `POST /v1/containers/{id}/consumers` | Containers → Detail → Register Consumer form | ✅ |
| 11 | `secret consumer list` | `GET /v1/containers/{id}/consumers` | Containers → Detail → Consumers table | ✅ |
| 12 | `secret consumer delete` | `DELETE /v1/containers/{id}/consumers` | Containers → Detail → Remove consumer button | ✅ |
| 13 | `secret order create` | `POST /v1/orders` | Orders → Create (key / asymmetric / certificate) | ✅ |
| 14 | `secret order list` | `GET /v1/orders` | Orders → List (with pagination) | ✅ |
| 15 | `secret order get` | `GET /v1/orders/{id}` | Orders → Detail (metadata + generated secret link) | ✅ |
| 16 | `secret order delete` | `DELETE /v1/orders/{id}` | Orders → Detail → Delete button | ✅ |

## Special Features Beyond CLI

| Feature | Description |
|---------|-------------|
| **Key-Value Editor** | Create/view secrets as key-value pairs (stored as JSON payload) |
| **JSON Editor** | Full graphical JSON editor (tree, code, form views) powered by JSONEditor — similar to HashiCorp Vault |
| **Multi-value Secrets** | Store complex structured data as JSON, edit graphically |
| **Payload Reveal** | Secret payloads are blurred by default, click to reveal (security) |
| **Search & Filter** | Filter secrets by name |
| **Pagination** | All list views are paginated |
| **Disk Cache** | Responses cached to minimize API calls, with automatic invalidation on mutations |

## Container Types Supported

| Type | Description |
|------|-------------|
| `generic` | Generic container with arbitrary secret references |
| `rsa` | RSA container (public key, private key, passphrase) |
| `certificate` | Certificate container (cert, intermediates, private key) |

## Order Types Supported

| Type | Description |
|------|-------------|
| `key` | Generate a symmetric key (AES, etc.) |
| `asymmetric` | Generate an asymmetric key pair (RSA, etc.) |
| `certificate` | Request a certificate |

