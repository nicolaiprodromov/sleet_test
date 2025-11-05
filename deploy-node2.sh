#!/bin/bash

set -e

echo "==================================="
echo "P2P Radio Node 2 Deployment"
echo "==================================="
echo ""

# Create directories for node2
echo "Creating directories for Node 2..."
mkdir -p data-node2/ipfs data-node2/hls data-node2/state data-node2/processed data-node2/certs data-node2/ipfs-staging

# Load node2 environment
if [ ! -f .env.node2 ]; then
    echo "ERROR: .env.node2 not found!"
    exit 1
fi

source .env.node2

echo "Node ID: ${NODE_ID}"
echo ""

echo "Starting Node 2 services..."
docker-compose -f docker-compose-node2.yml --env-file .env.node2 up -d

echo ""
echo "Waiting for Node 2 IPFS to initialize..."
sleep 10

# Get Node 1 IPFS peer ID and multiaddrs
echo ""
echo "Connecting Node 2 to Node 1's IPFS swarm..."
NODE1_IPFS_ID=$(docker exec p2p-radio-ipfs ipfs id -f='<id>')
NODE1_IPFS_ADDR=$(docker exec p2p-radio-ipfs ipfs id -f='<addrs>' | grep -v '127.0.0.1' | head -n1)

if [ ! -z "$NODE1_IPFS_ID" ]; then
    echo "Node 1 IPFS ID: $NODE1_IPFS_ID"
    
    # Connect the two IPFS nodes
    # First get node1's container IP
    NODE1_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' p2p-radio-ipfs)
    
    if [ ! -z "$NODE1_IP" ]; then
        echo "Node 1 IP: $NODE1_IP"
        CONNECT_ADDR="/ip4/${NODE1_IP}/tcp/4001/p2p/${NODE1_IPFS_ID}"
        echo "Connecting to: $CONNECT_ADDR"
        
        docker exec p2p-radio-ipfs-node2 ipfs swarm connect "$CONNECT_ADDR" || echo "Connection will be established automatically"
    fi
fi

echo ""
echo "==================================="
echo "Node 2 Deployment Complete!"
echo "==================================="
echo ""
echo "Node ID: ${NODE_ID}"
echo "Web Interface: http://localhost:81"
echo "IPFS Gateway: http://localhost:8081"
echo "IPFS API: http://localhost:5002"
echo ""
echo "To view logs: docker-compose -f docker-compose-node2.yml logs -f"
echo "To stop: docker-compose -f docker-compose-node2.yml down"
echo ""
echo "Both nodes should now be syncing via IPFS PubSub topic: p2p-radio-stream"
echo ""
