# auth-service — Study Notes

---

## Table of Contents

1. [How This Service Works](#1-how-this-service-works)
2. [Docker Basics](#2-docker-basics)
3. [Dockerfile — Line by Line](#3-dockerfile--line-by-line)
4. [The Commented Multi-Stage Build](#4-the-commented-multi-stage-build)
5. [Q&A](#5-qa)

---

## 1. How This Service Works

### What it does

The auth-service is the **identity gatekeeper** of the Lavenbloom platform. Every other service relies on it to verify who a user is. It does two things:

1. **Registration** — accepts a username and password, hashes the password using bcrypt, and stores the user in a PostgreSQL database
2. **Login** — accepts a username and password, verifies the hash, and returns a **JWT (JSON Web Token)** that the user includes in all future requests to other services

### API routes

| Method | Path | What it does |
|---|---|---|
| `GET` | `/health` | Returns `{"status": "ok"}` — used by Kubernetes to confirm the service is alive |
| `POST` | `/register` | Creates a new user. Returns 400 if username already exists |
| `POST` | `/login` | Validates credentials. Returns a JWT token. Returns 401 if wrong password |

### What is a JWT?

A **JWT (JSON Web Token)** is a signed string that proves identity. It looks like:
```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMSIsImV4cCI6MTY5....<signature>
```

It has three parts separated by `.`:
1. **Header** — base64-encoded JSON describing the algorithm (`{"alg":"HS256","typ":"JWT"}`)
2. **Payload** — base64-encoded JSON containing claims (`{"sub":"user1","exp":1690000000}`)
3. **Signature** — HMAC-SHA256 of header+payload, signed with `JWT_SECRET`

Other services (habit-service, journal-service, etc.) receive this token in the `Authorization: Bearer <token>` header. They verify the signature using the same `JWT_SECRET` — if valid, they trust the identity inside.

**Why not sessions?** Microservices are stateless — they don't share a session store. JWTs are self-contained (the token itself contains identity), so any service can verify a token independently without calling auth-service again.

### What is bcrypt?

`bcrypt` is a password hashing algorithm designed to be **slow on purpose**. It adds a random salt (so two identical passwords produce different hashes) and runs many iterations. Even if an attacker steals the database, they cannot reverse the hashes to get passwords. The `python-jose` library is used for JWT creation/verification.

### Database

A PostgreSQL database (`auth_db`) with a `users` table containing: `id`, `username`, `hashed_password`. The SQLAlchemy ORM handles queries — no raw SQL in the application code.

### How it connects to other components

```
User → Gateway (port 30080) → /auth/* → auth-service:8000 → PostgreSQL auth-db:5432
                                              ↑
                              JWT_SECRET env var from Kubernetes Secret
```

### Test suite

Located in `tests/test_auth.py`. Uses an in-memory SQLite database (instead of PostgreSQL) so tests run without needing a real database. Covers: health check, registration, duplicate registration rejection, successful login, wrong password rejection. Run with: `pytest --cov=app`.

---

## 2. Docker Basics

### What is Docker?

Docker is a tool that packages an application and all its dependencies into a **container** — a lightweight, isolated process. Unlike a virtual machine, a container does not include a full operating system — it shares the host OS kernel, making it much faster and smaller.

### Key concepts

**Image:** A read-only template for creating containers. Built from a `Dockerfile`. Layers are stacked: each instruction in a Dockerfile adds a layer.

**Container:** A running instance of an image. You can run many containers from one image. When a container stops, any data written inside it is lost (unless using volumes).

**Registry:** A storage server for images. Docker Hub (`hub.docker.com`) is the default public registry. This project stores images at `rnld101/lavenbloom-auth-service`.

**Layer caching:** Docker caches each layer. If a layer hasn't changed, Docker reuses it instead of rebuilding. This is why you always `COPY requirements.txt` and `RUN pip install` BEFORE `COPY app/ app/` — source code changes frequently but dependencies don't.

**Base image:** The starting point of your image. `python:3.11-slim` is a Debian-based image with Python 3.11 pre-installed. `slim` means non-essential packages are removed — smaller size, fewer CVEs.

**Tag:** A label on an image: `rnld101/lavenbloom-auth-service:dev-abc123`. The tag after `:` distinguishes versions. Without a tag, Docker assumes `latest` — avoid using `latest` in production because it's mutable (the same tag can point to different images over time).

### Core Docker commands

```bash
# Build an image from the Dockerfile in the current directory
docker build -t myapp:v1 .

# Run a container from an image
docker run -p 8000:8000 -e JWT_SECRET=mysecret myapp:v1

# List running containers
docker ps

# View container logs
docker logs <container-id>

# Open a shell inside a running container
docker exec -it <container-id> /bin/bash

# Push to Docker Hub (requires login first)
docker login
docker push myapp:v1

# Pull an image from registry
docker pull python:3.11-slim
```

### What does `docker build` do step by step?

1. Reads `Dockerfile` top to bottom
2. For each instruction: checks cache → if hit, skips rebuild; if miss, executes
3. Each instruction creates a new **layer** (a filesystem diff)
4. Final result is an image: a stack of layers with metadata

### Volumes vs bind mounts

**Volume:** Managed by Docker, stored in Docker's storage area. Persists after container stop. Used in production (Kubernetes PVCs are volumes).

**Bind mount:** Maps a host directory into the container. Used in development (`docker run -v $(pwd)/app:/app`) so code changes are reflected immediately.

---

## 3. Dockerfile — Line by Line

```dockerfile
FROM python:3.11-slim
```
**`FROM`** — Sets the base image. Every instruction after this builds on top of this image. `python:3.11-slim` is Debian Bookworm with Python 3.11 pre-installed, `slim` variant removes documentation, locales, and non-essential packages. Size: ~130MB vs ~300MB for the full image.

Why Python 3.11? It's the version specified in CI (`python-version: '3.10'` in SAST, though the image uses 3.11 — the runtime version). 3.11 introduced significant performance improvements over 3.10.

---

```dockerfile
WORKDIR /app
```
**`WORKDIR`** — Sets the working directory for all subsequent instructions (`RUN`, `COPY`, `CMD`). Creates the directory if it doesn't exist. Without this, every `COPY` and `RUN` would need an absolute path like `/app/...`. Think of it as `cd /app` that persists.

---

```dockerfile
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*
```
**`RUN`** — Executes a shell command during the image build. This installs OS-level build dependencies:
- `gcc` — C compiler. Required to compile Python packages that have C extensions (like `psycopg2`)
- `libpq-dev` — PostgreSQL client library headers. Required to compile `psycopg2` (Python-to-PostgreSQL driver)
- `&& rm -rf /var/lib/apt/lists/*` — Deletes the apt package index cache. Reduces image size by ~20MB. This must be in the same `RUN` instruction (same layer) as `apt-get update` — otherwise the cache deletion is in a separate layer and Docker's layer caching would still include the downloaded cache in a prior layer.

**Why one `RUN` for all three operations?** Each `RUN` creates a new image layer. If you split them into three instructions, the intermediate layers with the package cache are preserved in the final image even if you delete files in a later layer. Combining into one `RUN` with `&&` keeps the cleanup in the same layer that created the mess.

---

```dockerfile
COPY requirements.txt .
```
**`COPY`** — Copies files from the build context (your local directory) into the image. `requirements.txt` is copied to `/app/requirements.txt` (because `WORKDIR` is `/app`).

**Why copy `requirements.txt` before the app code?** Layer caching. If you copy all files first and then run `pip install`, every code change invalidates the pip install layer. By copying only `requirements.txt` first and running `pip install`, the pip install layer is only invalidated when `requirements.txt` changes — which is infrequent.

---

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```
Installs all Python packages listed in `requirements.txt`.

- `--no-cache-dir` — pip normally caches downloaded packages in `~/.cache/pip`. This flag disables that cache. Since we're inside a Docker build (one-time use), the cache is useless and just wastes space in the image layer.

---

```dockerfile
COPY app/ app/
```
Copies the entire `app/` directory from your local machine to `/app/app/` inside the image. This is done **after** pip install so that code changes don't invalidate the dependency installation layer.

---

```dockerfile
RUN useradd -m appuser && chown -R appuser /app
USER appuser
```
**Security hardening — two steps:**

`useradd -m appuser` — creates a new system user named `appuser`. `-m` creates a home directory at `/home/appuser`.

`chown -R appuser /app` — gives `appuser` ownership of the `/app` directory and all its contents. Recursive (`-R`).

`USER appuser` — all subsequent instructions and the container runtime use this user instead of root.

**Why not run as root?** If an attacker exploits a vulnerability in the application (e.g., code injection), they would execute code as `root` inside the container. A root escape from the container could mean root on the host. Running as a non-root user limits the damage: the attacker gets only `appuser` privileges — cannot write to system directories, cannot install packages, cannot read other users' files.

---

```dockerfile
EXPOSE 8000
```
**`EXPOSE`** — Documents that the container listens on port 8000. This is **documentation only** — it does NOT actually open the port. The actual port mapping happens at container runtime with `docker run -p 8000:8000` or in Kubernetes via the Service and `containerPort` in the Deployment spec.

---

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
**`CMD`** — The default command to run when the container starts. Uses JSON array format (exec form) — the command runs directly without a shell, which means:
- Signals (like SIGTERM from `docker stop`) are sent directly to the process — clean shutdown
- No shell overhead
- No shell injection risk

- `uvicorn` — ASGI server for FastAPI. Like Gunicorn but async-capable
- `app.main:app` — `app/main.py` file, `app` FastAPI instance inside it
- `--host 0.0.0.0` — listen on all network interfaces (not just localhost). Without this, the app only accepts connections from within the container — impossible to reach from Kubernetes
- `--port 8000` — the port number matching `EXPOSE 8000`

**`CMD` vs `ENTRYPOINT`:** `CMD` provides defaults that can be overridden at `docker run`. `ENTRYPOINT` sets the main executable that cannot be replaced (only its arguments can). Using `CMD` here allows developers to override the command for debugging: `docker run myapp uvicorn app.main:app --reload`.

---

## 4. The Commented Multi-Stage Build

The Dockerfile contains a commented-out multi-stage build alternative. Understanding this is important:

```dockerfile
# Stage 1: Builder (has compiler tools)
# FROM python:3.11-slim AS builder
# WORKDIR /app
# RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*
# COPY requirements.txt .
# RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime (no compiler tools)
# FROM python:3.11-slim
# WORKDIR /app
# COPY --from=builder /install /usr/local  # Copy only installed packages
# COPY app/ app/
# ...
```

### Why multi-stage builds?

`gcc` and `libpq-dev` are only needed to **compile** the Python packages. They are not needed to **run** the packages. In the single-stage build (currently active), these tools remain in the final image — they add ~50MB and increase the attack surface.

Multi-stage builds let you:
1. **Stage 1 (builder):** Install compilers, compile packages, build artifacts
2. **Stage 2 (runtime):** Copy only the compiled output — no compilers, no build tools

The final image only contains what's needed to run the app. The builder stage is discarded after build.

### Why is the single-stage build used instead?

For this project's scale, the size difference (~50MB) is acceptable. The single-stage build is simpler to understand and maintain. In a larger organisation with strict image size policies (e.g., all images must be <200MB), the multi-stage build would be enforced.

---

## 5. Q&A

**Q: Why is `python:3.11-slim` chosen over `python:3.11-alpine`?**
A: Alpine uses `musl libc` instead of `glibc`. Many Python C extensions (including `psycopg2`) are compiled against `glibc` and require compilation from source on Alpine. This makes builds slower and more complex. `slim` (Debian-based) is a good balance: smaller than the full Debian image, but compatible with pre-compiled Python wheels. Alpine is appropriate for very simple Python apps with no C extensions.

**Q: What is the difference between `RUN` and `CMD`?**
A: `RUN` executes during the image **build** — its effects are baked into the image layer (installed packages, created files, etc.). `CMD` specifies what runs when a **container starts** from the image — it's not executed during build. One image can have many `RUN` instructions but should have only one `CMD`.

**Q: If `EXPOSE 8000` doesn't open a port, what does it do?**
A: It serves as documentation embedded in the image metadata. `docker inspect myimage` shows the exposed ports. Tools like `docker run -P` (capital P) use `EXPOSE` ports to auto-assign host ports. In Kubernetes, `containerPort` in the Deployment spec serves the same documentation purpose — the actual port binding is handled by the Service.

**Q: Why does `requirements.txt` get copied before `app/`?**
A: Docker layer caching. Each `COPY` instruction creates a cache key based on the file contents. If `requirements.txt` hasn't changed, Docker uses the cached `pip install` layer even if `app/*.py` files changed. This makes rebuilds fast — pip install (which downloads from the internet) is skipped on every code change.

**Q: What happens if `JWT_SECRET` is not set as an environment variable?**
A: `auth.py` reads `os.getenv("JWT_SECRET")` — if not set, it returns `None`. Python-jose would then fail to create tokens (None is not a valid signing key), raising a runtime error on the first login attempt. In Kubernetes, the Secret is always injected via `envFrom.secretRef`, so this only fails in local development if you forget to set the env var.
