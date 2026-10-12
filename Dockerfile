# syntax=docker/dockerfile:1
FROM python:3.12.10-slim-bookworm AS builder
ENV PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV=/opt/solc-home \
    SOLC_SELECT_DIR=/opt/solc-home/.solc-select \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
RUN python -m venv /opt/venv
COPY requirements.lock pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements.lock
COPY sentinel ./sentinel
RUN pip install --no-cache-dir --no-deps . \
    && python -m solc_select install 0.8.30 0.8.20 0.7.6

FROM python:3.12.10-slim-bookworm AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV=/opt/solc-home \
    SOLC_SELECT_DIR=/opt/solc-home/.solc-select \
    SENTINEL_DATA_DIR=/data \
    SENTINEL_ENV=production \
    SENTINEL_DEBUG=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN groupadd --gid 10001 sentinel \
    && useradd --uid 10001 --gid sentinel --create-home sentinel \
    && mkdir -p /data /app /opt/solc-home
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=10001:10001 /opt/solc-home /opt/solc-home
COPY --chown=10001:10001 samples /app/samples
RUN chown 10001:10001 /data /app
USER 10001:10001
WORKDIR /app
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=3)"
CMD ["python", "-m", "sentinel.server"]
