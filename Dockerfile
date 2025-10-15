FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements/base.txt requirements/prod.txt ./
RUN pip install --no-cache-dir -r prod.txt

# Copy application
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Create directories with proper permissions BEFORE switching to app user
RUN mkdir -p /app/uploads/profile_images /app/uploads/service_images /app/alembic/versions && \
    chmod -R 777 /app/uploads /app/alembic

# Create non-root user and give ownership
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
