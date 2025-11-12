#!/bin/bash

set -e

echo "==================================="
echo "SleetBubble Setup Service"
echo "==================================="
echo ""

IPFS_API="${IPFS_API:-http://ipfs:5001}"
NODE_ID="${NODE_ID:-node1}"
MAX_RETRIES=30
RETRY_DELAY=2

echo "Node ID: ${NODE_ID}"
echo "IPFS API: ${IPFS_API}"
echo ""

wait_for_ipfs() {
    echo "Waiting for IPFS to be ready..."
    local retries=0
    
    while [ $retries -lt $MAX_RETRIES ]; do
        if curl -s -X POST "${IPFS_API}/api/v0/id" > /dev/null 2>&1; then
            echo "✓ IPFS is ready"
            return 0
        fi
        
        retries=$((retries + 1))
        echo "Waiting for IPFS... (attempt $retries/$MAX_RETRIES)"
        sleep $RETRY_DELAY
    done
    
    echo "ERROR: IPFS failed to start after $MAX_RETRIES attempts"
    return 1
}

import_shared_key() {
    echo ""
    echo "Importing shared IPNS key..."
    
    local KEY_FILE="/workspace/keys/sleetbubble-sex.key"
    local KEY_NAME="sleetbubble-sex"
    
    if [ ! -f "$KEY_FILE" ]; then
        echo "ERROR: Shared key file not found at $KEY_FILE"
        exit 1
    fi
    
    local existing_key=$(curl -s -X POST "${IPFS_API}/api/v0/key/list" | grep -o "\"${KEY_NAME}\"")
    
    if [ -n "$existing_key" ]; then
        echo "✓ Shared key '${KEY_NAME}' already exists"
    else
        curl -s -X POST \
            -F "file=@${KEY_FILE}" \
            "${IPFS_API}/api/v0/key/import?arg=${KEY_NAME}" > /dev/null
        
        if [ $? -eq 0 ]; then
            echo "✓ Shared key '${KEY_NAME}' imported successfully"
        else
            echo "ERROR: Failed to import shared key"
            exit 1
        fi
    fi
    
    local key_id=$(curl -s -X POST "${IPFS_API}/api/v0/key/list" | grep -A 1 "\"${KEY_NAME}\"" | grep -o '"Id":"[^"]*"' | cut -d'"' -f4)
    if [ -n "$key_id" ]; then
        echo "IPNS ID: ${key_id}"
    fi
}

run_setup_processor() {
    echo ""
    echo "Running setup processor..."
    
    if [ ! -f /workspace/setup.config.json ]; then
        echo "ERROR: setup.config.json not found"
        exit 1
    fi
    
    if [ ! -f /workspace/playlist.config.json ]; then
        echo "WARNING: playlist.config.json not found"
    fi
    
    python3 /src/setup/setup_processor.py || {
        echo "ERROR: Setup processor failed"
        exit 1
    }
    
    echo "✓ Setup processor complete"
}



create_setup_marker() {
    echo ""
    echo "Creating setup completion marker..."
    touch /state/.setup_complete
    echo "✓ Setup marker created"
}

main() {
    if wait_for_ipfs; then
        import_shared_key
        run_setup_processor
        create_setup_marker
        
        echo ""
        echo "==================================="
        echo "✓ Setup Complete!"
        echo "==================================="
        echo ""
        echo "SleetBubble node is ready to stream"
        echo "Node ID: ${NODE_ID}"
        echo "IPFS Gateway: http://localhost:8080"
        echo ""
        echo "IPFS configuration applied from: ipfs.config.json"
        echo "Stream info will be available at: data/state/stream_info.json"
        echo ""
        echo "Note: Shared IPNS key imported for deterministic publishing"
        echo ""
    else
        echo "Setup failed: IPFS not available"
        exit 1
    fi
}

main
