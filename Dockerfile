# ===========================================
# AI-crew Aegra Server Dockerfile
# ===========================================

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Aegra from GitHub
RUN pip install --no-cache-dir git+https://github.com/ibbybuilds/aegra.git

# Copy application code
COPY graphs/ ./graphs/
COPY aegra.json .

# Create non-root user
RUN useradd -m -u 1000 aicrew && chown -R aicrew:aicrew /app
USER aicrew

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start Aegra server
CMD ["aegra", "start", "--config", "/app/aegra.json"]
