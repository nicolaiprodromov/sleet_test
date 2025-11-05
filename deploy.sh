#!/bin/bash

set -e

echo "==================================="
echo "P2P Radio Node Deployment"
echo "==================================="
echo ""

if [ ! -f .env ]; then
    echo "Creating .env file..."
    NODE_ID="node-$(date +%s)"
    if [ -f .env.example ]; then
        cp .env.example .env
        sed -i "s/NODE_ID=node1/NODE_ID=${NODE_ID}/" .env
    else
        cat > .env << EOF
NODE_ID=${NODE_ID}
IPFS_API=http://ipfs:5001
IPFS_GATEWAY=http://ipfs:8080
STREAM_TOPIC=p2p-radio-stream
EOF
    fi
    echo "Generated NODE_ID: ${NODE_ID}"
fi

source .env

echo "Node ID: ${NODE_ID}"
echo ""

mkdir -p data/ipfs data/music data/hls data/state data/processed data/certs

echo "Checking for music files..."
if [ ! "$(ls -A data/music)" ]; then
    echo ""
    echo "WARNING: No music files found in data/music/"
    echo "Please add music files before starting the node."
    echo ""
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "Starting IPFS and preparing music library..."
docker-compose up -d ipfs

echo "Waiting for IPFS to be ready..."
sleep 10

echo ""
echo "Processing and pinning music files..."
docker-compose run --rm liquidsoap python3 /scripts/prepare-music.py /music /data/processed

echo ""
echo "Starting all services..."
docker-compose up -d

echo ""
echo "==================================="
echo "Deployment Complete!"
echo "==================================="
echo ""
echo "Node ID: ${NODE_ID}"
echo "Web Interface: http://localhost"
echo "IPFS Gateway: http://localhost:8080"
echo "IPFS API: http://localhost:5001"
echo ""
echo "To view logs: docker-compose logs -f"
echo "To stop: docker-compose down"
echo ""
