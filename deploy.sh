#!/bin/bash

set -e

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

echo "==================================="
echo "P2P Radio Node Deployment (IPNS)"
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
IPNS_LIFETIME=24h
IPNS_TTL=10s
PLAYLIST_UPDATE_INTERVAL=2
MAX_SEGMENTS=200
EOF
    fi
    echo "Generated NODE_ID: ${NODE_ID}"
fi

source .env

echo "Node ID: ${NODE_ID}"
echo ""

mkdir -p data/ipfs data/music data/hls data/state data/processed data/certs data/ipfs-staging

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

echo "Building Docker images with layer caching..."
docker compose build --parallel

echo ""
echo "Starting IPFS node..."
docker compose up -d ipfs

echo "Waiting for IPFS to be ready..."
sleep 20

echo "Checking IPFS status..."
docker exec p2p-radio-ipfs ipfs id || {
    echo "ERROR: IPFS failed to start"
    exit 1
}

echo ""
echo "Configuring IPFS for Docker networking..."
docker exec p2p-radio-ipfs ipfs config Addresses.API /ip4/0.0.0.0/tcp/5001
docker exec p2p-radio-ipfs ipfs config Addresses.Gateway /ip4/0.0.0.0/tcp/8080

echo "Configuring CORS headers..."
docker exec p2p-radio-ipfs ipfs config --json Gateway.HTTPHeaders.Access-Control-Allow-Origin '["*"]'
docker exec p2p-radio-ipfs ipfs config --json Gateway.HTTPHeaders.Access-Control-Allow-Methods '["GET", "POST", "PUT"]'
docker exec p2p-radio-ipfs ipfs config --json API.HTTPHeaders.Access-Control-Allow-Origin '["*"]'
docker exec p2p-radio-ipfs ipfs config --json API.HTTPHeaders.Access-Control-Allow-Methods '["GET", "POST", "PUT"]'

echo "Restarting IPFS with new configuration..."
docker compose restart ipfs
sleep 10

echo ""
echo "Processing and pinning music files..."
docker compose run --rm liquidsoap python3 /src/liquidsoap/prepare-music.py /music /data/processed || true

echo ""
echo "Building playlist from config..."
docker compose run --rm liquidsoap python3 /src/playlist/build-playlist.py /workspace/playlist.config.json /music /music/playlist.m3u || {
    echo "Warning: Playlist build failed, continuing..."
}

echo ""
echo "==================================="
echo "Initializing IPNS Keys"
echo "==================================="

if [ ! -f data/state/ipns_keys.json ]; then
    echo "Creating IPNS keys for mutable playlists..."
    docker compose run --rm playlist-generator python3 /src/playlist-generator/init-ipns.py
    
    if [ -f data/state/ipns_keys.json ]; then
        echo ""
        echo "✓ IPNS keys created successfully!"
        echo ""
        echo "Your permanent stream URLs:"
        cat data/state/ipns_keys.json
    else
        echo "ERROR: Failed to create IPNS keys"
        exit 1
    fi
else
    echo "✓ IPNS keys already exist"
fi

echo ""
echo "Enabling IPFS PubSub..."
docker compose exec -T ipfs ipfs config --json Experimental.Libp2pStreamMounting true || true
docker compose exec -T ipfs ipfs config --json Pubsub.Enabled true || true
docker compose exec -T ipfs ipfs config Pubsub.Router gossipsub || true

echo ""
echo "Starting all services..."
docker compose up -d

echo ""
echo "Waiting for services to initialize..."
sleep 10

echo ""
echo "==================================="
echo "Deployment Complete!"
echo "==================================="
echo ""
echo "Node ID: ${NODE_ID}"
echo "IPFS Gateway: http://localhost:8080"
echo ""
echo "IPNS Stream URLs (saved in data/state/stream_info.json):"
if [ -f data/state/stream_info.json ]; then
    cat data/state/stream_info.json | grep -E '(master_playlist_ipns|ipns)' || echo "(waiting for first playlist generation...)"
else
    echo "(waiting for first playlist generation...)"
fi
echo ""
echo "IPNS Streaming Mode: ENABLED"
echo "- Segments uploaded to IPFS in real-time"
echo "- Playlists published to IPNS (mutable)"
echo "- Continuous streaming with permanent URLs"
echo "- Access via: http://localhost:8080/ipns/YOUR_IPNS_NAME"
echo ""
echo "To view logs: docker compose logs -f"
echo "To check IPNS keys: cat data/state/ipns_keys.json"
echo "To check stream info: cat data/state/stream_info.json"
echo "To stop: docker compose down"
echo ""
