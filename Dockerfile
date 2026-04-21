FROM python:3.12-slim

# Dépendances système pour Playwright / Chromium
RUN apt-get update && apt-get install -y \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copier uniquement les fichiers nécessaires
COPY job-hunter/ ./job-hunter/

# Installer les dépendances Python
RUN pip install --no-cache-dir \
    flask==3.1.1 \
    openai \
    pyyaml==6.0.2 \
    requests==2.32.3 \
    playwright==1.52.0 \
    playwright-stealth==1.0.6 \
    beautifulsoup4==4.13.4 \
    gunicorn

# Installer Chromium via Playwright
RUN playwright install chromium --with-deps

# Variables d'environnement
ENV PYTHONPATH=/app/job-hunter
ENV FLASK_SECRET_KEY=change-me-in-production

EXPOSE 5000

# Utiliser shell form pour supporter $PORT
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --timeout 120 --workers 1 --threads 4 api.index:app
