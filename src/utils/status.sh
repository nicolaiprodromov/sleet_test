#!/bin/bash

echo "==================================="
echo "P2P Radio Node Status"
echo "==================================="
echo ""

source .env 2>/dev/null || true

echo "Node ID: ${NODE_ID:-Not configured}"
echo ""

echo "Container Status:"
docker-compose ps

echo ""
echo "IPFS Status:"
curl -s http://localhost:5001/api/v0/id | jq -r '.ID' 2>/dev/null || echo "IPFS not responding"

echo ""
echo "Stream Status:"
if [ -f "data/state/current_position.json" ]; then
    cat data/state/current_position.json | jq .
else
    echo "No state file found"
fi

echo ""
echo "Recent HLS segments:"
ls -lht data/hls/*.ts 2>/dev/null | head -5 || echo "No segments found"

echo ""
echo "Pinned content count:"
curl -s http://localhost:5001/api/v0/pin/ls?type=recursive | jq '.Keys | length' 2>/dev/null || echo "Cannot query IPFS"

echo ""
