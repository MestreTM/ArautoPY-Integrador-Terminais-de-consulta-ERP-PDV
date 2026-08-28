# ArautoPY — imagem única (painel, API, SC501, SC504)
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARAUTO_HOME=/data \
    ARAUTO_DOCKER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libfbclient2 \
      libpq5 \
      tini \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
 && pip install -r /app/requirements.txt

COPY . /app

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin arauto \
 && mkdir -p /data \
 && chown -R arauto:arauto /app /data

USER arauto
VOLUME ["/data"]

EXPOSE 6689 5589 6500 16510

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6689/', timeout=3).read(1)"

ENTRYPOINT ["tini", "--"]
CMD ["python", "run.py"]
