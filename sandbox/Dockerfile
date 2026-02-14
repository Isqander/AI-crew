# ===========================================
# AI-crew Sandbox — Docker-in-Docker
# ===========================================
# Runs as a privileged container with access to Docker daemon.
# Used for isolated code execution (tests, lint, arbitrary code).
#
# Two modes:
#   1. DinD (Docker-in-Docker) — privileged, runs its own Docker daemon
#   2. Docker socket mount      — mounts host /var/run/docker.sock
#
# Default: socket mount (simpler, less overhead).
# For DinD: use docker:dind as base and enable --privileged.

FROM python:3.11-slim

WORKDIR /app

# Install Docker CLI (for communicating with Docker daemon)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy sandbox code into package directory
COPY . ./sandbox/

# Pre-pull common images (optional — saves time on first execution)
# Uncomment if you want images ready at build time:
# RUN docker pull python:3.11-slim || true
# RUN docker pull node:20-slim || true

EXPOSE 8002

CMD ["uvicorn", "sandbox.server:app", "--host", "0.0.0.0", "--port", "8002"]
