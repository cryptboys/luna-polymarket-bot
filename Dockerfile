# Simple Dockerfile for Railway
FROM python:3.11-slim

WORKDIR /app

# Copy files
COPY requirements.txt .
COPY src/ ./src/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create data folder
RUN mkdir -p /app/data /app/logs

# Run bot
CMD ["python", "src/bot.py"]
