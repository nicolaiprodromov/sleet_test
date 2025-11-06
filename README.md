# P2P Decentralized Radio (IPFS/IPNS Streaming)

Fully decentralized radio station powered by IPFS, IPNS, and Liquidsoap.

## Architecture

This system streams audio entirely through IPFS using IPNS (InterPlanetary Name System) for mutable playlists:

1. **Liquidsoap** encodes audio → HLS segments (.ts files)
2. **hls-to-ipfs.py** uploads segments to IPFS (immutable CIDs)
3. **generate-ipns-playlist.py** creates HLS playlists referencing IPFS CIDs
4. **IPNS** publishes playlists to mutable names (permanent URLs)
5. Players fetch from `/ipns/YOUR_NAME` and get continuously updated playlists

## Quick Start

### Prerequisites
- Docker
- Docker Compose

### Setup

1. **Add your music files**
   ```bash
   cp your-music/* data/music/
   ```

2. **Configure your node (optional)**
   ```bash
   # Copy example environment file
   cp .env.example .env
   
   # Edit .env to customize NODE_ID and settings
   nano .env
   ```

3. **Start the node**
   ```bash
   docker compose up
   ```

   The setup service will automatically:
   - Configure IPFS with proper CORS headers
   - Initialize IPNS keys
   - Process and pin music files
   - Build playlists from configuration
   - Prepare all services for streaming

4. **Access your stream**
   - IPFS Gateway: http://localhost:8080
   - Stream: http://localhost:8080/ipns/YOUR_IPNS_NAME
   - Stream Info: `cat data/state/stream_info.json`

## Stream URLs

After deployment, you'll have permanent IPNS names:

```bash
# View your IPNS keys
cat data/state/ipns_keys.json

# View stream info with URLs
cat data/state/stream_info.json
```

Example stream URL:
```
http://localhost:8080/ipns/k51qzi5uqu5d...
```

Or via public gateways:
```
https://ipfs.io/ipns/k51qzi5uqu5d...
https://dweb.link/ipns/k51qzi5uqu5d...
```

## Management

```bash
# View logs
docker compose logs -f

# View specific service
docker compose logs -f playlist-generator

# Stop node
docker compose down

# Restart node
docker compose restart

# Restart just the setup (if needed)
docker compose up setup

# Check IPFS peers
docker exec p2p-radio-ipfs ipfs swarm peers

# List IPNS keys
docker exec p2p-radio-ipfs ipfs key list -l
```

## Stream Qualities

- **High (hifi)**: 192kbps AAC
- **Medium (midfi)**: 96kbps AAC  
- **Low (lofi)**: 64kbps AAC

Each quality has its own IPNS name for direct access.
