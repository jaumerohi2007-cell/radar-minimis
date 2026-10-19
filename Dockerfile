# API Python (FastAPI) en un contenedor ligero para Render, Fly.io, un VPS o cualquier PaaS con Docker.
# En la fase de validación a 0 €/mes la opción recomendada es Cloudflare Pages Functions + D1 (README §2).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY radar_minimis ./radar_minimis
COPY data_engine.py ./
RUN useradd --system --uid 10001 app && mkdir -p /app/data && chown app /app/data
USER app
ENV RM_DB_PATH=/app/data/radar.db BILLING_MODE=validation PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=4)" || exit 1
CMD ["sh", "-c", "exec .venv/bin/python data_engine.py serve --host 0.0.0.0 --port ${PORT}"]
