FROM debian:bullseye-slim AS base

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    liquidsoap \
    ffmpeg \
    curl \
    jq \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

FROM base AS dependencies

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

FROM base AS runtime

COPY --from=dependencies /usr/local /usr/local

WORKDIR /app

COPY src/liquidsoap/liquidsoap-wrapper.sh /app/
RUN chmod +x /app/liquidsoap-wrapper.sh

CMD ["/app/liquidsoap-wrapper.sh"]
