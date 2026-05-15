FROM python:3.11-slim

WORKDIR /app/backend

# System deps:
# - build-essential: compiling any C extensions
# - libjpeg-dev / zlib1g-dev / libfreetype6-dev: reportlab + Pillow image support
# - curl: container healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      libjpeg-dev \
      zlib1g-dev \
      libfreetype6-dev \
      curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8001/api/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
