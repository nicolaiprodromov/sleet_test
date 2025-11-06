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

prepare_music() {
    echo ""
    echo "Checking music directory..."
    
    if [ ! "$(ls -A /music)" ]; then
        echo "WARNING: No music files found in /music/"
        echo "Please add music files to data/music/ directory"
        return 0
    fi
    
    echo "Processing and pinning music files..."
    python3 /src/liquidsoap/prepare-music.py /music /data/processed || {
        echo "Warning: Music preparation had issues, continuing..."
    }
    
    echo "✓ Music processing complete"
}

build_playlist() {
    echo ""
    echo "Building playlist from configuration..."
    
    if [ ! -f /workspace/playlist.config.json ]; then
        echo "WARNING: No playlist.config.json found"
        return 0
    fi
    
    python3 /src/playlist/build-playlist.py /workspace/playlist.config.json /music /music/playlist.m3u || {
        echo "Warning: Playlist build had issues, continuing..."
    }
    
    echo "✓ Playlist built successfully"
}

initialize_ipns() {
    echo ""
    echo "==================================="
    echo "Initializing IPNS Keys"
    echo "==================================="
    
    if [ -f /state/ipns_keys.json ]; then
        echo "✓ IPNS keys already exist"
        echo ""
        echo "Your permanent stream URLs:"
        cat /state/ipns_keys.json
        return 0
    fi
    
    echo "Creating IPNS keys for mutable playlists..."
    python3 /src/playlist-generator/init-ipns.py
    
    if [ -f /state/ipns_keys.json ]; then
        echo ""
        echo "✓ IPNS keys created successfully!"
        echo ""
        echo "Your permanent stream URLs:"
        cat /state/ipns_keys.json
    else
        echo "ERROR: Failed to create IPNS keys"
        return 1
    fi
}

create_setup_marker() {
    echo ""
    echo "Creating setup completion marker..."
    touch /state/.setup_complete
    echo "✓ Setup marker created"
}

main() {
    if wait_for_ipfs; then
        prepare_music
        build_playlist
        initialize_ipns
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
        echo "IPNS keys are stored at: data/state/ipns_keys.json"
        echo ""
    else
        echo "Setup failed: IPFS not available"
        exit 1
    fi
}

main
