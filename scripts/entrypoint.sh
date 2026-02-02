#!/bin/sh
set -eu

log() {
  printf '%s | entrypoint | %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

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

export AEGRA_CONFIG LANGFUSE_ENABLED LANGFUSE_LOGGING
export POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
export PGDATA POSTGRES_LISTEN_ADDRESSES

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

    log "Ensuring database exists"
    export PGPASSWORD="${POSTGRES_PASSWORD}"
    gosu postgres psql -v ON_ERROR_STOP=1 \
      --username "${POSTGRES_USER}" --dbname postgres <<-EOSQL
        SELECT 'CREATE DATABASE ${POSTGRES_DB}'
        WHERE NOT EXISTS (
          SELECT FROM pg_database WHERE datname = '${POSTGRES_DB}'
        ) \gexec
EOSQL
    unset PGPASSWORD
    ;;
  *)
    log "External Postgres configured (host=${POSTGRES_HOST}), skipping local DB"
    ;;
esac

exec gosu aicrew python /app/start_aegra.py
