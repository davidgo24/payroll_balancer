# Build frontend
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Runtime
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ ./api/
COPY payroll_balancer/ ./payroll_balancer/

# Copy built frontend from builder
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Create data dir for SQLite (override via DATABASE_PATH on Railway with Volume)
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000
# Railway injects PORT at runtime; shell form expands it
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
