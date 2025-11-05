#!/bin/bash
set -e

echo "=========================================="
echo "P2P Radio IPNS Migration & Deployment"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}Error: Docker Compose is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker and Docker Compose found${NC}"
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating default .env file...${NC}"
    cat > .env << EOF
NODE_ID=node-$(date +%s)
IPNS_LIFETIME=24h
IPNS_TTL=30s
PLAYLIST_UPDATE_INTERVAL=3
MAX_SEGMENTS=50
SEGMENT_RETENTION_TIME=300
CLEANUP_INTERVAL=60
EOF
    echo -e "${GREEN}✓ Created .env file${NC}"
else
    echo -e "${GREEN}✓ .env file exists${NC}"
fi

# Load environment
source .env
echo -e "${GREEN}✓ Loaded configuration for node: ${NODE_ID}${NC}"
echo ""

# Create necessary directories
echo "Creating data directories..."
mkdir -p data/music
mkdir -p data/hls
mkdir -p data/state
mkdir -p data/ipfs
mkdir -p data/ipfs-staging
mkdir -p data/processed
mkdir -p data/certs

echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# Check if music exists
if [ -z "$(ls -A data/music)" ]; then
    echo -e "${YELLOW}⚠ Warning: No music files found in data/music/${NC}"
    echo "  Please add music files before starting the radio."
    echo ""
    read -p "Do you want to continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    MUSIC_COUNT=$(ls -1 data/music | wc -l)
    echo -e "${GREEN}✓ Found ${MUSIC_COUNT} files in data/music/${NC}"
fi

echo ""
echo "=========================================="
echo "Starting Services"
echo "=========================================="
echo ""

# Stop any running services
echo "Stopping any existing services..."
docker-compose down 2>/dev/null || true
echo ""

# Start IPFS first
echo "Starting IPFS node..."
docker-compose up -d ipfs

# Wait for IPFS to be ready
echo "Waiting for IPFS to initialize (30 seconds)..."
sleep 30

# Check IPFS health
echo "Checking IPFS node..."
if docker exec p2p-radio-ipfs ipfs id > /dev/null 2>&1; then
    IPFS_ID=$(docker exec p2p-radio-ipfs ipfs id -f='<id>')
    echo -e "${GREEN}✓ IPFS node is running${NC}"
    echo "  Node ID: ${IPFS_ID}"
else
    echo -e "${RED}✗ IPFS node failed to start${NC}"
    exit 1
fi

echo ""

# Initialize IPNS keys
echo "=========================================="
echo "Initializing IPNS Keys"
echo "=========================================="
echo ""

if [ ! -f data/state/ipns_keys.json ]; then
    echo "Creating IPNS keys for mutable playlists..."
    docker-compose run --rm playlist-generator python3 /scripts/init-ipns.py
    
    if [ -f data/state/ipns_keys.json ]; then
        echo -e "${GREEN}✓ IPNS keys created successfully${NC}"
        echo ""
        echo "Your permanent stream URLs:"
        echo "======================================"
        cat data/state/ipns_keys.json | python3 -m json.tool
        echo "======================================"
    else
        echo -e "${RED}✗ Failed to create IPNS keys${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ IPNS keys already exist${NC}"
    echo "  Using existing keys from data/state/ipns_keys.json"
fi

echo ""

# Start remaining services
echo "=========================================="
echo "Starting All Services"
echo "=========================================="
echo ""

echo "Starting liquidsoap, playlist generator, and other services..."
docker-compose up -d

echo ""
echo "Waiting for services to stabilize (10 seconds)..."
sleep 10

echo ""
echo "=========================================="
echo "Deployment Status"
echo "=========================================="
echo ""

# Check service status
SERVICES=("ipfs" "liquidsoap" "hls-uploader" "playlist-generator" "nginx" "stream-api")

for service in "${SERVICES[@]}"; do
    if docker-compose ps | grep "p2p-radio-${service}" | grep -q "Up"; then
        echo -e "${GREEN}✓ ${service} is running${NC}"
    else
        echo -e "${RED}✗ ${service} is not running${NC}"
    fi
done

echo ""
echo "=========================================="
echo "Access Information"
echo "=========================================="
echo ""
echo "Web Interface: http://localhost"
echo "IPFS Gateway:  http://localhost:8080"
echo "Stream Info:   http://localhost/state/stream_info.json"
echo ""

# Wait a bit and check for stream info
sleep 5

if [ -f data/state/stream_info.json ]; then
    echo "Stream is now available!"
    echo ""
    echo "IPNS Stream URLs:"
    cat data/state/stream_info.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
if 'master_playlist_ipns' in data:
    print(f\"  Master:  /ipns/{data['master_playlist_ipns']}\")
    print(f\"  URL:     {data['master_playlist_url']}\")
else:
    print('  Not yet available - check logs')
"
else
    echo -e "${YELLOW}⚠ Stream info not yet available${NC}"
    echo "  The system is still initializing. Check logs:"
    echo "  docker-compose logs -f playlist-generator"
fi

echo ""
echo "=========================================="
echo "Useful Commands"
echo "=========================================="
echo ""
echo "View logs:          docker-compose logs -f"
echo "Stop services:      docker-compose down"
echo "Restart services:   docker-compose restart"
echo "Check IPFS peers:   docker exec p2p-radio-ipfs ipfs swarm peers"
echo "List IPNS keys:     docker exec p2p-radio-ipfs ipfs key list -l"
echo ""

echo -e "${GREEN}=========================================="
echo "Deployment Complete! 🎉"
echo "==========================================${NC}"
echo ""
