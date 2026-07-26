# Use official Python runtime as base image
FROM python:3.10-slim

# Install system dependencies & Chromium headless browser
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libgconf-2-4 \
    libasound2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for Chromium & Python
ENV CHROME_BIN=/usr/bin/chromium
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot source code
COPY . .

# Run the Telegram bot entrypoint
CMD ["python", "-m", "bot.main"]
