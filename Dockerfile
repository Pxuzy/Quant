# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Build backend
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install runtime deps first (layer caching)
COPY pyproject.toml ./
RUN pip install --no-cache-dir fastapi uvicorn[standard] sqlalchemy pydantic alembic duckdb httpx requests pandas numpy pyarrow cachetools apscheduler

# Copy source
COPY backend/ backend/
COPY scripts/ scripts/
COPY README.md ./

# Install the package itself
RUN pip install --no-cache-dir .

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

EXPOSE 8000

ENV DATA_LAKE_DIR=/data/lake
ENV DUCKDB_PATH=/data/quant.duckdb
ENV DATABASE_URL=sqlite:////data/quant.db

VOLUME ["/data"]

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
