FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system ysa && useradd --system --gid ysa --create-home ysa
WORKDIR /app/apps/youtube-data-gateway
COPY apps/youtube-data-gateway/pyproject.toml ./
COPY apps/youtube-data-gateway/src ./src
RUN pip install --no-cache-dir .
USER ysa
EXPOSE 8080
CMD ["ysa-gateway"]
