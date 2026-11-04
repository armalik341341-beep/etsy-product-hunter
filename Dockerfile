# Etsy Product Hunter — production image (Render free tier)
FROM python:3.11-slim

WORKDIR /app

# system deps for lxml build (wheels usually cover it, kept minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HF Spaces injects nothing; it expects the app on 7860. Render injects $PORT.
# Default 7860 works for HF; $PORT override keeps Render compat.
ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}"]
