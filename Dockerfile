# Use an official, lightweight Python runtime as the base image
FROM python:3.11-slim-bookworm

# Set container metadata
LABEL maintainer="DevOps Team"
LABEL description="Production-ready container for Research Merge Orchestrator"

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Define application working directory
WORKDIR /app

# Install curl for container health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install dependencies without caching pip wheels to keep image minimal
RUN pip install --no-cache-dir -r requirements.txt

# Create non-privileged user and group for security
RUN groupadd -r appgroup && useradd -r -g appgroup -m -d /home/appuser appuser

# Copy application code and frontend assets with appropriate ownership
# We copy the entire workspace except what's in .dockerignore
COPY --chown=appuser:appgroup . .

# Switch to non-root execution
USER appuser

# Expose the FastAPI application port
EXPOSE 8000

# Health check targeting the dedicated status endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/status || exit 1

# Start server using Uvicorn pointing to the FastAPI app in main.py
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
