# MOZART Multi-Platform Handler — production image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# system deps (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# python deps first (better Docker layer caching)
COPY requirements.txt .
RUN pip install -r requirements.txt

# app code
COPY app.py caption_generator.py youtube_uploader.py hashtags.json ./
COPY templates ./templates
COPY static ./static

# persistent data dir (config.json, uploads/, output/) — mount a volume here
ENV DATA_DIR=/data
RUN mkdir -p /data && chown -R 1000:1000 /data

# Environment expected (set in Dokploy):
#   PUBLIC_BASE_URL    e.g. https://mozart.yourdomain.com
#   APP_USERNAME       login user
#   APP_PASSWORD       login password (use a long random string)
#   FLASK_SECRET_KEY   any long random string
#   PORT               default 5050

EXPOSE 5050

# Single worker because the app keeps a background queue thread in-process.
# Long timeout because reels can take a while to upload.
CMD ["gunicorn", "app:app", \
     "--bind", "0.0.0.0:5050", \
     "--workers", "1", \
     "--threads", "8", \
     "--timeout", "600", \
     "--access-logfile", "-", \
     "--error-logfile",  "-"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://127.0.0.1:5050/healthz || exit 1
