FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY bot.py ./

# Create data dir for persistence
RUN mkdir -p /data
VOLUME ["/data"]

# Default envs
ENV DATA_DIR=/data \
    PORT=8080 \
    HEALTHCHECK_PORT=8081

EXPOSE 8080 8081

# Expect TELEGRAM_BOT_TOKEN at runtime
CMD ["python", "bot.py"]