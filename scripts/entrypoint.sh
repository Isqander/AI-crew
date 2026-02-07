#!/bin/sh
set -eu

# ===========================================
# AI-crew Multi-Service Entrypoint
# Starts: PostgreSQL → supervisord (Aegra + nginx + Langfuse)
# ===========================================

log() {
  printf '%s | entrypoint | %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

# -----------------------------------------------------------
# Environment defaults
# -----------------------------------------------------------
: "${AEGRA_CONFIG:=/app/aegra.prod.json}"
: "${LANGFUSE_ENABLED:=false}"
: "${LANGFUSE_LOGGING:=false}"
: "${POSTGRES_HOST:=127.0.0.1}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_DB:=aicrew}"
: "${POSTGRES_USER:=aicrew}"
: "${POSTGRES_PASSWORD:=aicrew_secret_password}"
: "${PGDATA:=/var/lib/postgresql/data}"
: "${POSTGRES_LISTEN_ADDRESSES:=127.0.0.1}"

# Langfuse self-hosted defaults
: "${LANGFUSE_DB:=langfuse}"
: "${LANGFUSE_DATABASE_URL:=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${LANGFUSE_DB}}"
: "${LANGFUSE_NEXTAUTH_SECRET:=changeme-nextauth-secret}"
: "${LANGFUSE_SALT:=changeme-salt}"
: "${LANGFUSE_NEXTAUTH_URL:=http://localhost:3000}"

export AEGRA_CONFIG LANGFUSE_ENABLED LANGFUSE_LOGGING
export POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
export PGDATA POSTGRES_LISTEN_ADDRESSES

# -----------------------------------------------------------
# 1) PostgreSQL (local or external)
# -----------------------------------------------------------
case "${POSTGRES_HOST}" in
  127.0.0.1|localhost|::1)
    log "Local Postgres enabled (host=${POSTGRES_HOST}, port=${POSTGRES_PORT})"

    PG_BIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | head -n 1)"
    if [ -z "${PG_BIN}" ] || [ ! -x "${PG_BIN}/initdb" ]; then
      log "Postgres binaries not found in /usr/lib/postgresql"
      exit 1
    fi

    mkdir -p "${PGDATA}"
    chown -R postgres:postgres "${PGDATA}"
    chmod 700 "${PGDATA}"

    if [ ! -s "${PGDATA}/PG_VERSION" ]; then
      log "Initializing Postgres data directory"
      PWFILE="$(mktemp)"
      printf '%s' "${POSTGRES_PASSWORD}" > "${PWFILE}"
      chown postgres:postgres "${PWFILE}"
      chmod 600 "${PWFILE}"
      gosu postgres "${PG_BIN}/initdb" \
        -D "${PGDATA}" \
        --username="${POSTGRES_USER}" \
        --pwfile="${PWFILE}" \
        --auth-local=scram-sha-256 \
        --auth-host=scram-sha-256
      rm -f "${PWFILE}"
    fi

    log "Starting Postgres"
    gosu postgres "${PG_BIN}/pg_ctl" -D "${PGDATA}" \
      -o "-c listen_addresses=${POSTGRES_LISTEN_ADDRESSES} -p ${POSTGRES_PORT}" \
      -w start

    log "Ensuring databases exist"
    export PGPASSWORD="${POSTGRES_PASSWORD}"
    gosu postgres psql -v ON_ERROR_STOP=1 \
      --username "${POSTGRES_USER}" --dbname postgres <<-EOSQL
        SELECT 'CREATE DATABASE ${POSTGRES_DB}'
        WHERE NOT EXISTS (
          SELECT FROM pg_database WHERE datname = '${POSTGRES_DB}'
        ) \gexec
        SELECT 'CREATE DATABASE ${LANGFUSE_DB}'
        WHERE NOT EXISTS (
          SELECT FROM pg_database WHERE datname = '${LANGFUSE_DB}'
        ) \gexec
EOSQL
    unset PGPASSWORD
    ;;
  *)
    log "External Postgres configured (host=${POSTGRES_HOST}), skipping local DB"
    ;;
esac

# -----------------------------------------------------------
# 2) Generate supervisord config
# -----------------------------------------------------------
log "Generating supervisord configuration"

cat > /etc/supervisor/conf.d/aicrew.conf <<'CONF_AEGRA'
[program:aegra]
command=gosu aicrew python /app/scripts/start_aegra.py
directory=/app
autostart=true
autorestart=true
startretries=5
startsecs=5
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0

[program:nginx]
command=nginx -g "daemon off;"
autostart=true
autorestart=true
startretries=3
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
CONF_AEGRA

# --- Langfuse (conditional) ---
if [ "${LANGFUSE_ENABLED}" = "true" ] && [ -f /opt/langfuse/web/server.js ]; then
  log "Langfuse ENABLED — adding to supervisor"

  # Resolve the correct Prisma engine library for the current platform
  PRISMA_ENGINE=$(find /opt/langfuse -name "libquery_engine-debian*" 2>/dev/null | head -1)
  if [ -z "${PRISMA_ENGINE}" ]; then
    PRISMA_ENGINE=$(find /opt/langfuse -name "libquery_engine-linux*" 2>/dev/null | head -1)
  fi
  if [ -z "${PRISMA_ENGINE}" ]; then
    PRISMA_ENGINE=$(find /opt/langfuse -name "libquery_engine-*" 2>/dev/null | head -1)
  fi
  log "Prisma engine: ${PRISMA_ENGINE:-not found}"

  # Escape percent signs for supervisord (% → %%)
  SAFE_DB_URL=$(printf '%s' "${LANGFUSE_DATABASE_URL}" | sed 's/%/%%/g')
  SAFE_NEXTAUTH_SECRET=$(printf '%s' "${LANGFUSE_NEXTAUTH_SECRET}" | sed 's/%/%%/g')
  SAFE_SALT=$(printf '%s' "${LANGFUSE_SALT}" | sed 's/%/%%/g')
  SAFE_NEXTAUTH_URL=$(printf '%s' "${LANGFUSE_NEXTAUTH_URL}" | sed 's/%/%%/g')

  cat >> /etc/supervisor/conf.d/aicrew.conf <<CONF_LANGFUSE

[program:langfuse]
command=node web/server.js
directory=/opt/langfuse
autostart=true
autorestart=true
startretries=5
startsecs=5
environment=DATABASE_URL="${SAFE_DB_URL}",DIRECT_URL="${SAFE_DB_URL}",NEXTAUTH_SECRET="${SAFE_NEXTAUTH_SECRET}",SALT="${SAFE_SALT}",NEXTAUTH_URL="${SAFE_NEXTAUTH_URL}",HOSTNAME="0.0.0.0",PORT="3000",TELEMETRY_ENABLED="false",PRISMA_QUERY_ENGINE_LIBRARY="${PRISMA_ENGINE:-}"
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
CONF_LANGFUSE

elif [ "${LANGFUSE_ENABLED}" = "true" ]; then
  log "WARNING: LANGFUSE_ENABLED=true but /opt/langfuse/web/server.js not found"
else
  log "Langfuse disabled — skipping"
fi

# -----------------------------------------------------------
# 3) Start all services via supervisord
# -----------------------------------------------------------
log "Starting services: aegra, nginx$([ "${LANGFUSE_ENABLED}" = "true" ] && echo ", langfuse")"
exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
