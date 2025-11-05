FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

FROM base AS dependencies

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM base AS runtime

COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

WORKDIR /app

COPY src/state-sync/state-sync.py /app/

CMD ["python3", "/app/state-sync.py"]
