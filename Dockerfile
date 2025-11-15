FROM python:3.11-slim

# Prevents Python from writing pyc files and buffers logs immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install OS dependencies (if ReportLab needs fonts/libfreetype etc.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the source code
COPY . .

# Cloud Run provides the PORT env var; default to 8080 for local use
ENV PORT=8080

EXPOSE 8080

CMD ["bash", "-lc", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
