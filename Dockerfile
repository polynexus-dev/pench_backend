# Use Python 3.12 slim image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Placeholder so Django settings can load at image build time.
# The real SECRET_KEY is injected at runtime via docker-compose env.
ENV SECRET_KEY=build-time-placeholder-not-used-in-production

# Install system dependencies for GIS and Postgres
RUN apt-get update && apt-get install -y \
    binutils \
    libproj-dev \
    gdal-bin \
    libgdal-dev \
    python3-gdal \
    postgresql-client \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir daphne channels channels-redis gunicorn

# Copy project
COPY . /app/

# Strip Windows CR line endings from shell/python scripts that run in the container
RUN sed -i 's/\r$//' /app/entrypoint.sh \
    && sed -i 's/\r$//' /app/fix_migrations.py \
    && chmod +x /app/entrypoint.sh

EXPOSE 9083

ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]