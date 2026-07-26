FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Only the CA certificates and fonts are needed now that reverse-image search is
# handled by the Fluffle HTTP API (no more headless Chromium / Selenium).
RUN apt-get update && apt-get install -y \
    ca-certificates \
    fonts-liberation \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
