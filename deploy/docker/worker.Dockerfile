FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system ysa && useradd --system --gid ysa --create-home ysa
WORKDIR /app/apps/worker
COPY apps/worker/pyproject.toml ./
COPY apps/worker/src ./src
RUN pip install --no-cache-dir .
USER ysa
CMD ["python", "-m", "ysa_worker.main"]
