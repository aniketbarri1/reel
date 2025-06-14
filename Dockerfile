# Use lightweight Python image
FROM python:3.11-slim

# Set environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the project files
COPY . .

# Set env variables (optional override with Docker Compose or .env)
ENV TELEGRAM_TOKEN=your_bot_token_here

# Expose no ports (Telegram bot and scheduler only)
CMD ["python", "main.py"]
