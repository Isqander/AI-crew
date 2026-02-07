# ===========================================
# AI-crew Multi-Service Dockerfile
# Aegra API (8000) + Frontend (5173) + Langfuse (3000)
# ===========================================
# Build:
#   docker build -t aicrew .
# Run:
#   docker run -p 8000:8000 -p 5173:5173 -p 3000:3000 --env-file .env aicrew
#
# Build args:
#   VITE_API_URL        — API base for frontend (default: /api → nginx proxy)
#   AEGRA_PIP_SOURCE    — alternative pip source for Aegra package
# ===========================================

# ============================================================
# Stage 1: Build Frontend (Vite + React)
# ============================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /build

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ .

ARG VITE_API_URL=/api
RUN VITE_API_URL=${VITE_API_URL} npx vite build

# ============================================================
# Stage 2: Prepare Langfuse for Debian
# ============================================================
# Using Langfuse v2 — requires only PostgreSQL (no ClickHouse/Redis/S3).
# Langfuse v3+ requires ClickHouse, Redis, and S3 which is too heavy
# for a single-container deployment.
#
# The official image is Alpine-based (musl).
# We regenerate the Prisma query engine for Debian (glibc) below.

FROM langfuse/langfuse:2 AS langfuse-alpine

FROM node:20-slim AS langfuse-builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /langfuse
COPY --from=langfuse-alpine /app .

# Regenerate Prisma client for Debian/glibc
# The official Langfuse image ships Alpine/musl Prisma engines which won't
# work on the Debian-based final image. We:
#   1. Find the schema dynamically (pnpm monorepo layout varies)
#   2. Regenerate the Prisma client (produces a Debian engine)
#   3. Copy the Debian engine to every .prisma/client dir (pnpm store compat)
#   4. Remove musl engines so the runtime never picks them up
RUN set -e; \
    echo "=== Prisma Debian engine setup ==="; \
    # 1. Find schema
    SCHEMA=$(find /langfuse -name "schema.prisma" -path "*/prisma/*" 2>/dev/null | head -1); \
    echo "Schema: ${SCHEMA:-NOT FOUND}"; \
    # 2. Detect Prisma version from installed @prisma/client
    PRISMA_PKG=$(find /langfuse -path "*/@prisma/client/package.json" 2>/dev/null | head -1); \
    if [ -n "${PRISMA_PKG}" ]; then \
      PRISMA_VER=$(node -e "console.log(require('${PRISMA_PKG}').version)"); \
    else \
      PRISMA_VER="5.22.0"; \
    fi; \
    echo "Prisma version: ${PRISMA_VER}"; \
    # 3. Generate Prisma client for Debian
    if [ -n "${SCHEMA}" ]; then \
      npm install -g "prisma@${PRISMA_VER}" 2>/dev/null \
      && prisma generate --schema="${SCHEMA}" \
      && echo "OK: Prisma client regenerated for Debian/glibc"; \
    else \
      echo "WARN: No schema found — skipping prisma generate"; \
    fi; \
    # 4. Distribute Debian engine to ALL .prisma/client dirs (pnpm virtual store)
    DEBIAN_ENGINE=$(find /langfuse -name "libquery_engine-debian*" -type f 2>/dev/null | head -1); \
    if [ -n "${DEBIAN_ENGINE}" ]; then \
      echo "Debian engine: ${DEBIAN_ENGINE}"; \
      find /langfuse -path "*/.prisma/client" -type d | while read dir; do \
        cp -f "${DEBIAN_ENGINE}" "${dir}/" 2>/dev/null || true; \
        echo "  -> copied to ${dir}"; \
      done; \
    else \
      echo "WARN: No Debian Prisma engine found after generate"; \
    fi; \
    # 5. Remove musl engines to prevent loading incompatible binary
    MUSL_COUNT=$(find /langfuse -name "libquery_engine-linux-musl*" -type f 2>/dev/null | wc -l); \
    if [ "${MUSL_COUNT}" -gt 0 ]; then \
      find /langfuse -name "libquery_engine-linux-musl*" -type f -delete 2>/dev/null || true; \
      echo "Removed ${MUSL_COUNT} musl engine(s)"; \
    fi; \
    echo "=== Prisma setup complete ==="

# ============================================================
# Stage 3: Final Image
# ============================================================
FROM python:3.11-slim

WORKDIR /app

# Runtime defaults
ENV PYTHONUNBUFFERED=1 \
    AEGRA_CONFIG=/app/aegra.prod.json \
    LANGFUSE_ENABLED=false \
    LANGFUSE_LOGGING=false

# ---- System dependencies ----
# Includes: Node.js 20 (Langfuse runtime), nginx (frontend),
#           supervisor (multi-process), PostgreSQL (local DB option)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    gosu \
    postgresql \
    postgresql-contrib \
    supervisor \
    nginx \
    openssl \
    ca-certificates \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ---- Python dependencies ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Aegra ----
ARG AEGRA_PIP_SOURCE=""
COPY vendor/ /app/vendor/
RUN if [ -n "${AEGRA_PIP_SOURCE}" ]; then \
      pip install --no-cache-dir "${AEGRA_PIP_SOURCE}"; \
    elif [ -d /app/vendor/aegra ]; then \
      pip install --no-cache-dir /app/vendor/aegra; \
    else \
      echo "Aegra source not found. Provide vendor/aegra or set AEGRA_PIP_SOURCE." >&2; \
      exit 1; \
    fi

# ---- Application code ----
COPY graphs/ ./graphs/
COPY aegra*.json .
COPY scripts/ /app/scripts/

# Align Aegra package layout and graphs path for runtime
RUN python - <<'PY'
import site
from pathlib import Path

site_dir = Path(site.getsitepackages()[0])
src_dir = site_dir / "src"
src_dir.mkdir(exist_ok=True)
init_file = src_dir / "__init__.py"
if not init_file.exists():
    init_file.write_text("__path__ = __import__('pkgutil').extend_path(__path__, __name__)\n")

agent_server_dir = site_dir / "agent_server"
src_agent_server = src_dir / "agent_server"
if agent_server_dir.exists() and not src_agent_server.exists():
    try:
        src_agent_server.symlink_to(agent_server_dir, target_is_directory=True)
    except Exception:
        import shutil
        shutil.copytree(agent_server_dir, src_agent_server)

graphs_source = Path("/app/graphs")
graphs_link = Path("/usr/local/lib/python3.11/graphs")
if graphs_source.exists() and not graphs_link.exists():
    try:
        graphs_link.symlink_to(graphs_source, target_is_directory=True)
    except Exception:
        import shutil
        shutil.copytree(graphs_source, graphs_link)
PY

# ---- Frontend (built static files) ----
COPY --from=frontend-builder /build/dist /app/frontend/dist

# ---- Langfuse (Debian-ready build) ----
COPY --from=langfuse-builder /langfuse /opt/langfuse

# ---- nginx config ----
COPY scripts/nginx-frontend.conf /etc/nginx/conf.d/frontend.conf
RUN rm -f /etc/nginx/sites-enabled/default

# ---- Prepare runtime dirs ----
RUN useradd -m -u 1000 aicrew \
    && chown -R aicrew:aicrew /app \
    && mkdir -p /var/log/supervisor /var/run

# ---- Ports ----
EXPOSE 8000 5173 3000

# ---- Health check (Aegra + Frontend) ----
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8000/health > /dev/null \
     && curl -sf http://localhost:5173/ > /dev/null \
     || exit 1

RUN chmod +x /app/scripts/entrypoint.sh
CMD ["/app/scripts/entrypoint.sh"]
