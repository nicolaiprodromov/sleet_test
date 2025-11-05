#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

CONFIG_FILE="${1:-$PROJECT_ROOT/playlist.config.json}"
MUSIC_DIR="${2:-$PROJECT_ROOT/data/music}"
OUTPUT_FILE="${3:-$PROJECT_ROOT/data/music/playlist.m3u}"

echo "Rebuilding playlist..."
echo "Config: $CONFIG_FILE"
echo "Music dir: $MUSIC_DIR"
echo "Output: $OUTPUT_FILE"

docker compose run --rm liquidsoap python3 /src/playlist/build-playlist.py /workspace/playlist.config.json /music /music/playlist.m3u

echo ""
echo "Playlist rebuilt! Liquidsoap will automatically reload it."
