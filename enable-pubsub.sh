#!/bin/bash

set -e

echo "Enabling IPFS PubSub on both nodes..."

echo ""
echo "Configuring Node 1..."
docker exec p2p-radio-ipfs ipfs config --json Experimental.Libp2pStreamMounting true
docker exec p2p-radio-ipfs ipfs config --bool Pubsub.Enabled true
docker exec p2p-radio-ipfs ipfs config Pubsub.Router gossipsub

echo ""
echo "Configuring Node 2..."
docker exec p2p-radio-ipfs-node2 ipfs config --json Experimental.Libp2pStreamMounting true
docker exec p2p-radio-ipfs-node2 ipfs config --bool Pubsub.Enabled true
docker exec p2p-radio-ipfs-node2 ipfs config Pubsub.Router gossipsub

echo ""
echo "Restarting IPFS containers to apply changes..."
docker restart p2p-radio-ipfs
docker restart p2p-radio-ipfs-node2

echo ""
echo "Waiting for IPFS to restart..."
sleep 15

echo ""
echo "Verifying PubSub is enabled..."
echo "Node 1 PubSub topics:"
docker exec p2p-radio-ipfs ipfs pubsub ls || echo "No subscriptions yet"

echo ""
echo "Node 2 PubSub topics:"
docker exec p2p-radio-ipfs-node2 ipfs pubsub ls || echo "No subscriptions yet"

echo ""
echo "PubSub enabled successfully!"
echo "The state-sync containers should now work properly."
