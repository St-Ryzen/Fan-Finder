# Fan Finder - Railway Deployment Dockerfile
# This creates a containerized environment with Python, Chrome, and all dependencies

# Use official Python 3.11 slim image as base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99 \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Install system dependencies including Chrome
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chrome and dependencies
    chromium \
    chromium-driver \
    # Additional libraries for Chrome
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libxrender1 \
    libxi6 \
    libxtst6 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxss1 \
    libxcomposite1 \
    libxdamage1 \
    # Utility tools
    wget \
    curl \
    unzip \
    git \
    # Virtual display for headless Chrome
    xvfb \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for better Docker layer caching)
COPY app/backend/requirements.txt /app/app/backend/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/app/backend/requirements.txt

# Copy the entire application
COPY . /app

# Create necessary directories
RUN mkdir -p /app/app/config /app/app/data

# Expose port (Railway will assign this dynamically via $PORT)
EXPOSE 5000

# Start virtual display and run the Flask application
CMD Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp & \
    python app/backend/app.py
