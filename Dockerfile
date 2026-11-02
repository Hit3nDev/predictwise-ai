# One container: the React app is built once, then served by the FastAPI backend.
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 FRONTEND_DIST=/app/frontend-dist
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend-dist
# Data lives in a volume so uploads, models and the database survive restarts.
VOLUME ["/data"]
WORKDIR /data
ENV PYTHONPATH=/app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health')"
CMD ["python", "-m", "uvicorn", "main:app", "--app-dir", "/app", "--host", "0.0.0.0", "--port", "8000"]
