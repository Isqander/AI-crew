# ===========================================
# AI-crew Aegra Server Dockerfile
# ===========================================

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Runtime defaults for containerized deployments
ENV PYTHONUNBUFFERED=1 \
    AEGRA_CONFIG=/app/aegra.prod.json \
    LANGFUSE_ENABLED=false \
    LANGFUSE_LOGGING=false

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    gosu \
    postgresql \
    postgresql-contrib \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Aegra (default: PyPI)
ARG AEGRA_PIP_SOURCE="aegra==0.1.0"
RUN pip install --no-cache-dir "${AEGRA_PIP_SOURCE}"

# Copy application code
COPY graphs/ ./graphs/
COPY aegra*.json .
COPY scripts/start_aegra.py /app/start_aegra.py
COPY scripts/entrypoint.sh /app/entrypoint.sh

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

# Create non-root user
RUN useradd -m -u 1000 aicrew && chown -R aicrew:aicrew /app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start Aegra server (and local Postgres when enabled)
RUN chmod +x /app/entrypoint.sh
CMD ["/app/entrypoint.sh"]
