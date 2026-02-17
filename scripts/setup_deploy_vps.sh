#!/usr/bin/env bash
# =============================================================================
# Setup Deploy VPS for AI-crew generated applications
# =============================================================================
#
# This script configures a fresh VPS to receive deployments from AI-crew.
# It installs Docker, Traefik reverse proxy, and sets up the deploy user.
#
# Prerequisites:
#   - Ubuntu 22.04+ or Debian 12+
#   - Root or sudo access
#   - SSH access
#
# Usage:
#   ssh root@<VPS_IP> 'bash -s' < scripts/setup_deploy_vps.sh
#
# After running, add the VPS SSH key to GitHub Secrets:
#   - VPS_SSH_KEY: contents of ~/.ssh/id_ed25519 (deploy user)
#   - VPS_HOST: <VPS_IP>
#   - VPS_USER: deploy
#
# =============================================================================

set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
TRAEFIK_EMAIL="${TRAEFIK_EMAIL:-admin@example.com}"
DOMAIN_IP="${DOMAIN_IP:-$(curl -s ifconfig.me)}"

echo "=== AI-crew Deploy VPS Setup ==="
echo "Deploy user: $DEPLOY_USER"
echo "Server IP: $DOMAIN_IP"
echo "Traefik email: $TRAEFIK_EMAIL"
echo ""

# --- 1. Install Docker ---
if ! command -v docker &>/dev/null; then
    echo ">>> Installing Docker..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg lsb-release
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable docker
    echo "Docker installed: $(docker --version)"
else
    echo "Docker already installed: $(docker --version)"
fi

# --- 2. Create deploy user ---
if ! id "$DEPLOY_USER" &>/dev/null; then
    echo ">>> Creating deploy user: $DEPLOY_USER"
    useradd -m -s /bin/bash "$DEPLOY_USER"
    usermod -aG docker "$DEPLOY_USER"

    # Generate SSH key for the deploy user
    sudo -u "$DEPLOY_USER" ssh-keygen -t ed25519 -f "/home/$DEPLOY_USER/.ssh/id_ed25519" -N "" -q
    echo "Deploy user SSH key generated at /home/$DEPLOY_USER/.ssh/id_ed25519"
else
    echo "Deploy user '$DEPLOY_USER' already exists"
    usermod -aG docker "$DEPLOY_USER"
fi

# --- 3. Create apps directory ---
APP_DIR="/home/$DEPLOY_USER/apps"
mkdir -p "$APP_DIR"
chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
echo "Apps directory: $APP_DIR"

# --- 4. Setup Traefik ---
TRAEFIK_DIR="/home/$DEPLOY_USER/traefik"
mkdir -p "$TRAEFIK_DIR/config"
mkdir -p "$TRAEFIK_DIR/acme"
touch "$TRAEFIK_DIR/acme/acme.json"
chmod 600 "$TRAEFIK_DIR/acme/acme.json"

# Create docker network for Traefik
docker network create traefik-public 2>/dev/null || true

# Traefik docker-compose
cat > "$TRAEFIK_DIR/docker-compose.yml" <<TRAEFIK_COMPOSE
version: '3.8'

services:
  traefik:
    image: traefik:v2.11
    container_name: traefik
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./acme:/acme
      - ./config:/config
    command:
      - "--api.dashboard=false"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--providers.docker.network=traefik-public"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--entrypoints.web.http.redirections.entrypoint.to=websecure"
      - "--entrypoints.web.http.redirections.entrypoint.scheme=https"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web"
      - "--certificatesresolvers.letsencrypt.acme.email=${TRAEFIK_EMAIL}"
      - "--certificatesresolvers.letsencrypt.acme.storage=/acme/acme.json"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
    networks:
      - traefik-public

networks:
  traefik-public:
    external: true
TRAEFIK_COMPOSE

chown -R "$DEPLOY_USER:$DEPLOY_USER" "$TRAEFIK_DIR"

# Start Traefik
cd "$TRAEFIK_DIR"
docker compose up -d
echo "Traefik started"

# --- 5. Setup GitHub Actions self-hosted runner (optional) ---
echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Add to GitHub Secrets:"
echo "     VPS_SSH_KEY: $(cat /home/$DEPLOY_USER/.ssh/id_ed25519)"
echo "     VPS_HOST: $DOMAIN_IP"
echo "     VPS_USER: $DEPLOY_USER"
echo ""
echo "  2. Add the deploy user's public key to authorized_keys:"
echo "     cat /home/$DEPLOY_USER/.ssh/id_ed25519.pub >> /home/$DEPLOY_USER/.ssh/authorized_keys"
echo ""
echo "  3. Deploy URL pattern: https://<app-name>.$DOMAIN_IP.nip.io"
echo ""
echo "  4. Apps will be deployed to: $APP_DIR/<app-name>/"
echo ""
