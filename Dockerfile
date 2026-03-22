# ---- Stage 1: Build React dashboard ----
FROM node:20-slim AS frontend

WORKDIR /frontend
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund
COPY dashboard/ ./
RUN npm run build

# ---- Stage 2: Install Python dependencies ----
FROM python:3.12-slim AS backend

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 3: Runtime ----
FROM python:3.12-slim

LABEL maintainer="data-engineering"
LABEL description="AI Investment Research Assistant — API + Dashboard"

WORKDIR /app

# Python packages
COPY --from=backend /install /usr/local

# Application code
COPY app/ ./app/
COPY .env.example ./.env

# Built dashboard static files
COPY --from=frontend /frontend/dist ./static/

# Non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
