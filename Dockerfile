FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy package files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install package
RUN pip install --no-cache-dir -e ".[dev]"

# Create directories
RUN mkdir -p /app/packs /app/results /app/suites

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV EVAL_HARNESS_HOME=/app

# Default command
CMD ["toolkit-eval", "--help"]
