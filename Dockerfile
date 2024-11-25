FROM python:3.11-slim AS builder

# Install poetry and dependencies
ENV POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Install required system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install poetry using the official installer
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="$POETRY_HOME/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy only dependency files first
COPY pyproject.toml poetry.lock* ./

# Install dependencies
RUN poetry install --no-root --no-dev && rm -rf $POETRY_CACHE_DIR

# Copy the rest of the application
COPY app app/

FROM python:3.11-slim AS runtime

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv" \
    VAULT_PATH="/data/vault"

# Create non-root user and setup vault directory with proper permissions
RUN useradd --create-home appuser && \
    mkdir -p /data/vault && \
    chown -R appuser:appuser /data && \
    chmod -R 755 /data

# Copy virtual environment and application from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/app /app/app

# Set working directory
WORKDIR /app

# Switch to non-root user
USER appuser

# Create volume for vault data
VOLUME ["/data/vault"]

# Expose the application port
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]