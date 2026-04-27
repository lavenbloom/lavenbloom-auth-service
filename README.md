# lavenbloom-auth-service

> **Runbook & Developer Walkthrough** — Authentication microservice for the Lavenbloom platform.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [API Reference](#api-reference)
4. [Environment Variables](#environment-variables)
5. [Local Development Walkthrough](#local-development-walkthrough)
6. [Docker Walkthrough](#docker-walkthrough)
7. [Running Tests](#running-tests)
8. [CI/CD Pipeline Walkthrough](#cicd-pipeline-walkthrough)
9. [Kubernetes Deployment](#kubernetes-deployment)
10. [Secrets Management](#secrets-management)
11. [Troubleshooting](#troubleshooting)

---

## Overview

`auth-service` is a **FastAPI** microservice responsible for all user identity operations in the Lavenbloom platform. It handles:

- User **registration** with bcrypt password hashing
- User **login** with JWT access token issuance
- Health check endpoint used by Kubernetes probes

It is the **source of truth for identity** — downstream services (`habit-service`, `journal-service`) validate JWTs independently using a shared `JWT_SECRET` without calling back to `auth-service` at runtime.

| Property | Value |
|---|---|
| **Runtime** | Python 3.11 |
| **Framework** | FastAPI |
| **Database** | PostgreSQL 15 |
| **Auth** | JWT (HS256), bcrypt |
| **Port** | `8000` |
| **Docker image** | `lavenbloom/lavenbloom-auth-service` |

---

## Architecture

```
┌──────────────┐         ┌──────────────────┐         ┌─────────────────┐
│   Client /   │ ──────▶ │   auth-service   │ ──────▶ │   PostgreSQL    │
│   Frontend   │  HTTP   │  FastAPI :8000   │  SQLAlchemy  │  (auth_db)      │
└──────────────┘         └──────────────────┘         └─────────────────┘
                                  │
                          issues JWT token
                                  │
                    ┌─────────────▼──────────────┐
                    │  habit-service / journal-   │
                    │  service (verify locally)   │
                    └────────────────────────────┘
```

### Source Layout

```
auth-service/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI routes (register, login, health)
│   ├── auth.py          # bcrypt hashing + JWT creation/verification
│   ├── database.py      # SQLAlchemy engine + session factory
│   ├── models.py        # User ORM model (id, username, email, hashed_password)
│   └── schemas.py       # Pydantic request/response schemas
├── tests/
│   └── test_auth.py     # 5 pytest tests (health, register, duplicate, login ok, login fail)
├── Dockerfile
├── requirements.txt
└── sonar-project.properties
```

---

## API Reference

### `GET /health`

Returns service liveness status.

```bash
curl http://localhost:8001/health
# {"status":"ok"}
```

---

### `POST /register`

Creates a new user account.

**Request body:**
```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "securepassword123"
}
```

**Success — `201 Created`:**
```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com"
}
```

**Error — `400 Bad Request`:**
```json
{ "detail": "Username already registered" }
{ "detail": "Email already registered" }
```

---

### `POST /login`

Authenticates a user and returns a Bearer JWT token.

**Request (form-encoded `application/x-www-form-urlencoded`):**
```
username=alice&password=securepassword123
```

**Success — `200 OK`:**
```json
{
  "access_token": "<JWT>",
  "token_type": "bearer"
}
```

**Error — `401 Unauthorized`:**
```json
{ "detail": "Incorrect username or password" }
```

> **Token lifetime:** 60 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES = 60`).  
> **JWT payload:** `{ "sub": "<username>", "id": "<user_id>", "exp": <unix_ts> }`.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `POSTGRES_URI` | ✅ | `postgresql://user:password@localhost/auth_db` | Full PostgreSQL connection string |
| `JWT_SECRET` | ✅ | `supersecretjwtkey` | HS256 signing secret — **must match** all downstream services |

> ⚠️ Never use the default `JWT_SECRET` in production. Set via Kubernetes Secret (`auth-service-secret`).

---

## Local Development Walkthrough

### Prerequisites

- Python 3.11+
- PostgreSQL 15 running locally (or use Docker Compose)
- `pip`

### Step 1 — Clone and install dependencies

```bash
git clone https://github.com/lavenbloom/lavenbloom-auth-service.git
cd lavenbloom-auth-service
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### Step 2 — Set environment variables

```bash
# Windows PowerShell:
$env:POSTGRES_URI = "postgresql://user:password@localhost:5432/auth_db"
$env:JWT_SECRET   = "devsecret"

# macOS/Linux:
export POSTGRES_URI="postgresql://user:password@localhost:5432/auth_db"
export JWT_SECRET="devsecret"
```

### Step 3 — Run the service

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Service starts at `http://localhost:8000`.  
Interactive Swagger docs at `http://localhost:8000/docs`.

### Step 4 — Quick smoke test

```bash
# Register a user
curl -X POST http://localhost:8000/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"pass1234"}'

# Login
curl -X POST http://localhost:8000/login \
  -d "username=testuser&password=pass1234"
```

---

## Docker Walkthrough

### Build the image

```bash
docker build -t lavenbloom-auth-service:local .
```

### Run with a local PostgreSQL

```bash
docker run -d \
  -e POSTGRES_URI="postgresql://user:password@host.docker.internal:5432/auth_db" \
  -e JWT_SECRET="devsecret" \
  -p 8001:8000 \
  lavenbloom-auth-service:local
```

### Run with Docker Compose (full stack)

From the project root:

```bash
docker compose up auth-db auth-service
```

Service is available at `http://localhost:8001`.

---

## Running Tests

Tests use an in-memory **SQLite** database — no PostgreSQL required.

```bash
# Install test dependencies (already in requirements.txt)
pip install pytest pytest-cov httpx

# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=app --cov-report=term-missing
```

### Test coverage (5 tests)

| Test | What it verifies |
|---|---|
| `test_health` | `GET /health` returns `200 {"status": "ok"}` |
| `test_register` | `POST /register` creates user, returns `201`, no password in response |
| `test_register_duplicate` | Duplicate username returns `400` |
| `test_login_success` | Valid credentials return `200` with `access_token` |
| `test_login_failure` | Wrong password returns `401` |

---

## CI/CD Pipeline Walkthrough

The pipeline is defined in `.github/workflows/ci-auth-service.yml` and calls **centralized reusable workflows** from `lavenbloom-shared`.

### Trigger → Job mapping

| Event | Jobs triggered |
|---|---|
| `pull_request` → `develop` or `main` | `sast` → `sca` → `trivy` → `pr-check` |
| `push` → `develop` | `dev-publish` → `dev-cd` |
| GitHub Release created | `publish` → `cd` |

### Pull Request flow (security gate)

```
PR opened / updated
      │
      ▼
  [sast] ── SonarQube scan + pytest coverage upload
      │
      ▼
  [sca]  ── Snyk dependency scan (Python requirements.txt)
      │
      ▼
  [trivy] ── Temporary Docker build + CVE scan (CRITICAL/HIGH)
      │
      ▼
  [pr-check] ── Aggregated pass/fail gate (required for merge)
```

### Develop push flow (dev deployment)

```
Push to develop
      │
      ▼
  [dev-publish] ── Build Docker image, tag as dev-{SHA}, push to Docker Hub
      │            Skips if tag already exists (dedup check)
      ▼
  [dev-cd] ── Clone lavenbloom-charts repo
              Update microservices/auth-service/values-dev.yaml
              Validate YAML (yq), commit and push
              ArgoCD detects commit → syncs dev cluster automatically
```

### Release flow (prod deployment)

```
GitHub Release created (e.g. v1.2.0)
      │
      ▼
  [publish] ── Build Docker image, tag as v1.2.0, push to Docker Hub
      │
      ▼
  [cd] ── Update values-prod.yaml with new semver tag
          ArgoCD syncs prod cluster
```

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `SONAR_TOKEN` | SonarQube authentication token |
| `SONAR_URL` | SonarQube server URL (e.g. `https://sonar.example.com`) |
| `SNYK_TOKEN` | Snyk API token for SCA |
| `DOCKER_USERNAME` | Docker Hub username |
| `DOCKER_PASSWORD` | Docker Hub password or access token |
| `HELM_REPO_PAT` | GitHub PAT with push access to `lavenbloom-charts` repo |

---

## Kubernetes Deployment

`auth-service` is deployed via ArgoCD using the Helm chart at `charts/microservices/auth-service/`.

### Manual Helm install (dev)

```bash
helm install auth-service ./microservices/auth-service -f values-dev.yaml
```

### Verify the deployment

```bash
# Check pod is running
kubectl get pods -n backend -l app=auth-service

# Check logs
kubectl logs -n backend deployment/auth-service

# Port-forward to test locally
kubectl port-forward -n backend deployment/auth-service 8001:8000

# Hit health endpoint
curl http://localhost:8001/health
```

### Check the Secret is mounted correctly

```bash
kubectl get secret auth-service-secret -n backend -o jsonpath='{.data.POSTGRES_URI}' | base64 -d
kubectl get secret auth-service-secret -n backend -o jsonpath='{.data.JWT_SECRET}' | base64 -d
```

### Namespace

`auth-service` runs in the `backend` namespace. Its database (`auth-db`) runs in the `db` namespace.  
Network policy allows only `auth-service` to reach `auth-db`.

---

## Secrets Management

| Secret Name (K8s) | Keys | Injected As |
|---|---|---|
| `auth-service-secret` | `POSTGRES_URI`, `JWT_SECRET` | `envFrom.secretRef` |
| `auth-db-secret` | `POSTGRES_USER`, `POSTGRES_PASSWORD` | PostgreSQL StatefulSet env |

> ⚠️ **Known Gap:** `values-dev.yaml` and `values-prod.yaml` contain plaintext secrets committed to the charts repo.  
> For production hardening, migrate to [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) or [External Secrets Operator](https://external-secrets.io/).

---

## Troubleshooting

### Service fails to start — `FATAL: database does not exist`

The database init Job may not have completed. Check:

```bash
kubectl get jobs -n db
kubectl logs job/auth-db-init -n db
```

Re-run the init job manually if needed.

### `401 Unauthorized` on all downstream services after rotating JWT_SECRET

The `JWT_SECRET` must be **identical** across `auth-service`, `habit-service`, and `journal-service`.  
After rotating the secret, redeploy all three services:

```bash
kubectl rollout restart deployment/auth-service -n backend
kubectl rollout restart deployment/habit-service -n backend
kubectl rollout restart deployment/journal-service -n backend
```

### `422 Unprocessable Entity` on `/login`

`/login` accepts `application/x-www-form-urlencoded` (OAuth2 form), **not** JSON.  
Use `-d "username=...&password=..."` with curl, or the Swagger `/docs` UI.

### SonarQube quality gate fails

- Ensure `sonar-project.properties` is correct and `SONAR_TOKEN` / `SONAR_URL` secrets are set.
- Tests must pass and produce `coverage.xml` before the scan step.
- Check the SonarQube dashboard for the specific failed condition.