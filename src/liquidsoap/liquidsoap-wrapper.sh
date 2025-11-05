#!/bin/bash

set -e

echo "Waiting for IPFS to be ready..."
until curl -sf -X POST "${IPFS_API}/api/v0/id" > /dev/null 2>&1; do
    sleep 2
done

echo "IPFS is ready. Starting Liquidsoap..."

mkdir -p /hls /state

exec liquidsoap /etc/liquidsoap/radio.liq
