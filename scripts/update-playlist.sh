#!/bin/bash

set -e

if [ -z "$1" ]; then
    echo "Usage: ./update-playlist.sh <manifest.json|ipfs_hash>"
    exit 1
fi

TARGET=$1

echo "Updating playlist from: ${TARGET}"

docker-compose exec liquidsoap python3 /scripts/update-playlist.py "${TARGET}" /music

echo "Reloading Liquidsoap..."
docker-compose restart liquidsoap

echo "Playlist updated successfully!"
