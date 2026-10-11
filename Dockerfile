FROM python:3.12-slim

ARG SOURCE_DIR=.
LABEL org.opencontainers.image.title="Pastillas" \
      org.opencontainers.image.description="Medicamentos, tomas, recetas y existencias en tu servidor" \
      org.opencontainers.image.source="https://github.com/kadyto/pastillas" \
      org.opencontainers.image.version="0.1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/pastillas.sqlite \
    PORT=8000

WORKDIR /app
# SOURCE_DIR permite tanto construir desde una carpeta como desde el .tar.gz de GitHub.
COPY ${SOURCE_DIR}/app ./app
RUN mkdir /data /backups && chown -R 10001:10001 /app /data /backups
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"
CMD ["python", "-m", "app.server"]
