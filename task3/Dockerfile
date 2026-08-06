FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY bench/ ./bench/
COPY scripts/ ./scripts/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ENV IMDB_RAW_DIR=/data/raw \
    IMDB_INDEX_DIR=/data/index \
    WORKERS=4 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2).status==200 else 1)"

ENTRYPOINT ["./entrypoint.sh"]
