# ===========================================
# AI-crew — Frontend (React + Vite) Production
# ===========================================
# Multi-stage: build with Node, serve with nginx.
#
# Build:
#   docker build --build-arg VITE_API_URL=https://gateway.example.com -t aicrew-frontend frontend/
# Run:
#   docker run -p 5173:80 aicrew-frontend

# ---- Stage 1: Build ----
FROM node:20-alpine AS builder

WORKDIR /build

COPY package*.json ./
RUN npm ci

COPY . .

# VITE_API_URL is baked into JS at build time
ARG VITE_API_URL=http://localhost:8081
RUN VITE_API_URL=${VITE_API_URL} npx vite build

# ---- Stage 2: Serve with nginx ----
FROM nginx:alpine

# Copy built files
COPY --from=builder /build/dist /usr/share/nginx/html

# nginx config for SPA (all routes → index.html)
RUN cat > /etc/nginx/conf.d/default.conf <<'NGINX'
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback: all non-file routes → index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Health check
    location /healthz {
        access_log off;
        return 200 "ok";
    }
}
NGINX

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost/healthz || exit 1
