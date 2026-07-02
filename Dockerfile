FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy package metadata and application code before installation.
COPY pyproject.toml README.md LICENSE ./
COPY loop_engine/ ./loop_engine/
RUN pip install --no-cache-dir .

# Create loop directories
RUN mkdir -p /app/.loop/{skills,state,worktrees}

# Set environment variables
ENV PYTHONPATH=/app
ENV LOOP_ENGINE_HOME=/app

# Default command
ENTRYPOINT ["loop-engine"]
CMD ["--help"]
