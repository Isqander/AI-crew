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

# Produce Debian/glibc Prisma query engine
#
# The official Langfuse image is Alpine (musl).  Its Next.js standalone
# output does NOT include @prisma/client's generator-build tooling, so
# `prisma generate` cannot run directly against the copied tree.
#
# Strategy:
#   1. Read schema.prisma from the Langfuse tree
#   2. Patch it (remove extra generators, add debian binaryTargets)
#   3. Run `prisma generate` inside a **fresh temporary npm project**
#      where @prisma/client is properly installed with all build files
#   4. Copy the resulting Debian engine binary into every location
#      where the Langfuse runtime searches for it
#   5. Remove musl engines so the runtime never loads them
RUN set -e; \
    echo "=== Prisma Debian engine setup ==="; \
    \
    # --- 1. Find schema ---
    SCHEMA=$(find /langfuse -name "schema.prisma" -path "*/prisma/*" 2>/dev/null | head -1); \
    if [ -z "${SCHEMA}" ]; then echo "ERROR: No schema.prisma found" && exit 1; fi; \
    echo "Schema: ${SCHEMA}"; \
    \
    # --- 2. Detect Prisma version ---
    PRISMA_PKG=$(find /langfuse -path "*/@prisma/client/package.json" 2>/dev/null | head -1); \
    if [ -n "${PRISMA_PKG}" ]; then \
      PRISMA_VER=$(node -e "console.log(require('${PRISMA_PKG}').version)"); \
    else \
      PRISMA_VER="5.22.0"; \
    fi; \
    echo "Prisma version: ${PRISMA_VER}"; \
    \
    # --- 3. Prepare a clean temp project with patched schema ---
    mkdir -p /tmp/pgen; \
    cp "${SCHEMA}" /tmp/pgen/schema.prisma; \
    cd /tmp/pgen; \
    \
    # 3a. Remove non-client generators (prisma-erd-generator etc.)
    node -e " \
      const fs = require('fs'); \
      let s = fs.readFileSync('schema.prisma', 'utf8'); \
      s = s.replace(/generator\s+(?!client[\s{])\w+\s*\{[^}]*\}/g, ''); \
      fs.writeFileSync('schema.prisma', s); \
      console.log('Removed non-client generators'); \
    "; \
    # 3b. Add binaryTargets for debian
    if grep -q 'binaryTargets' schema.prisma; then \
      sed -i 's/binaryTargets\s*=\s*\[.*\]/binaryTargets = ["native", "debian-openssl-3.0.x"]/' schema.prisma; \
    else \
      sed -i '/provider\s*=.*prisma-client-js/a\  binaryTargets = ["native", "debian-openssl-3.0.x"]' schema.prisma; \
    fi; \
    echo "--- Patched generator ---"; \
    grep -A5 'generator client' schema.prisma | head -6; \
    echo "---"; \
    \
    # --- 4. Generate in temp project (has full @prisma/client) ---
    npm init -y > /dev/null 2>&1; \
    npm install "prisma@${PRISMA_VER}" "@prisma/client@${PRISMA_VER}" --save-exact > /dev/null 2>&1; \
    npx prisma generate --schema=schema.prisma; \
    echo "OK: prisma generate succeeded"; \
    \
    # --- 5. Distribute FULL generated Prisma Client to Langfuse ---
    # We must copy the ENTIRE .prisma/client/ directory, not just the
    # engine binary.  The generated index.js contains binaryTargets
    # configuration that tells Prisma which engine to load at runtime.
    GEN_CLIENT=$(find /tmp/pgen -path "*/.prisma/client" -type d 2>/dev/null | head -1); \
    if [ -z "${GEN_CLIENT}" ]; then \
      echo "ERROR: No generated .prisma/client directory" && exit 1; \
    fi; \
    echo "Generated client dir: ${GEN_CLIENT}"; \
    DEBIAN_ENGINE=$(find "${GEN_CLIENT}" -name "libquery_engine-debian*" -type f 2>/dev/null | head -1); \
    if [ -z "${DEBIAN_ENGINE}" ]; then \
      echo "ERROR: No Debian engine in generated client" && exit 1; \
    fi; \
    echo "Engine: ${DEBIAN_ENGINE}"; \
    cd /langfuse; \
    # 5a. Replace all .prisma/client directories with the regenerated one
    find /langfuse -path "*/.prisma/client" -type d 2>/dev/null | while read dir; do \
      cp -af "${GEN_CLIENT}"/* "${dir}/" 2>/dev/null || true; \
      echo "  -> replaced ${dir}"; \
    done; \
    # 5b. Copy engine binary to @prisma/client and packages/shared/prisma
    for pattern in "*/@prisma/client" "*/packages/shared/prisma"; do \
      find /langfuse -path "${pattern}" -type d 2>/dev/null | while read dir; do \
        cp -f "${DEBIAN_ENGINE}" "${dir}/" 2>/dev/null || true; \
        echo "  -> engine to ${dir}"; \
      done; \
    done; \
    \
    # --- 6. Remove musl engines ---
    find /langfuse -name "libquery_engine-linux-musl*" -type f -delete 2>/dev/null || true; \
    echo "Removed musl engine(s)"; \
    \
    # --- 7. Verify ---
    echo "Debian engines in /langfuse:"; \
    find /langfuse -name "libquery_engine-debian*" -type f; \
    echo "Musl engines remaining:"; \
    find /langfuse -name "libquery_engine-linux-musl*" -type f 2>/dev/null || echo "  (none)"; \
    \
    # --- Cleanup ---
    rm -rf /tmp/pgen; \
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

# ---- Prisma CLI (for Langfuse database migrations at startup) ----
RUN npm install -g prisma@5.22.0 2>/dev/null

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
