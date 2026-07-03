# ──────────────────────────────────────────────
# LLMGov Gateway — Multi-stage Dockerfile
# ──────────────────────────────────────────────
# Stage 1: Install dependencies in a clean layer
# Stage 2: Copy app code on top — cache-friendly
# ──────────────────────────────────────────────

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── Stage 1: Dependencies ──
FROM base AS deps

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# ── Stage 2: Application ──
FROM deps AS runtime

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
