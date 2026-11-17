# MCP server image. Heroku builds it from heroku.yml; locally: docker build -t sales-mcp .
# Contains only the server's code (mcp_server/, embed/, database/) and the ONNX model, never
# data/ or pipeline code. Configuration (DATABASE_URL, MCP_ALLOWED_HOSTS) comes from the environment.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.hf \
    EMBED_BACKEND=onnx \
    MCP_HOST=0.0.0.0

WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY embed/ embed/
COPY database/ database/
COPY mcp_server/ mcp_server/

# Download the pinned model at build time, then forbid downloads at runtime.
RUN python -c "from embed.model import _load_onnx; _load_onnx()" && chmod -R a+rX /app
ENV HF_HUB_OFFLINE=1

# Heroku runs containers as a non-root user and sets PORT.
RUN useradd --create-home app
USER app
CMD ["python", "-m", "mcp_server.server"]
