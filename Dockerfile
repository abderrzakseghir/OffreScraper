FROM python:3.12-slim

# Dépendances système pour Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    fonts-liberation libatk-bridge2.0-0 libatk1.0-0 \
    libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 \
    libgbm1 libglib2.0-0 libgtk-3-0 libnspr4 libnss3 \
    libpango-1.0-0 libpangocairo-1.0-0 libx11-6 libx11-xcb1 \
    libxcb1 libxcomposite1 libxcursor1 libxdamage1 libxext6 \
    libxfixes3 libxi6 libxrandr2 libxrender1 libxss1 libxtst6 \
    fonts-unifont fonts-ubuntu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copier le code
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

# Installer le navigateur Chromium (léger, ~170 Mo)
RUN playwright install chromium --with-deps

# Variables d'environnement
ENV PYTHONPATH=/app/job-hunter
ENV FLASK_SECRET_KEY=change-me-in-railway-env

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "120", "--workers", "1", "--threads", "4", "job-hunter.api.index:app"]
