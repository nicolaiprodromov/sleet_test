#!/bin/sh
set -e

echo "Applying SleetBubble IPFS configuration..."

CONFIG_FILE="/ipfs-config/ipfs.config.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Warning: Configuration file not found at $CONFIG_FILE"
    echo "Skipping custom configuration"
    exit 0
fi

echo "Reading configuration from $CONFIG_FILE"

ipfs config Addresses.API "$(cat $CONFIG_FILE | grep -A 2 '"Addresses"' | grep '"API"' | cut -d'"' -f4)"
ipfs config Addresses.Gateway "$(cat $CONFIG_FILE | grep -A 3 '"Addresses"' | grep '"Gateway"' | cut -d'"' -f4)"

ipfs config --json API.HTTPHeaders.Access-Control-Allow-Origin '["*"]'
ipfs config --json API.HTTPHeaders.Access-Control-Allow-Methods '["GET", "POST", "PUT"]'
ipfs config --json API.HTTPHeaders.Access-Control-Allow-Headers '["*"]'

ipfs config --json Gateway.HTTPHeaders.Access-Control-Allow-Origin '["*"]'
ipfs config --json Gateway.HTTPHeaders.Access-Control-Allow-Methods '["GET", "POST", "PUT"]'
ipfs config --json Gateway.HTTPHeaders.Access-Control-Allow-Headers '["*"]'

ipfs config --json Experimental.Libp2pStreamMounting true
ipfs config --json Pubsub.Enabled true
ipfs config Pubsub.Router gossipsub

echo "✓ SleetBubble IPFS configuration applied successfully"
