# Sleetbubble: Technical Architecture Specification
## Decentralized P2P Radio Consensus Engine

**Purpose:** Technical implementation guide for building the consensus layer on top of existing IPFS streaming infrastructure.

**Status:** Final Specification
**Date:** November 6, 2025
**Version:** 2.0

---

## Executive Summary

Sleetbubble is a decentralized P2P radio streaming platform where independent nodes collectively determine the global playlist through Byzantine Fault Tolerant (BFT) consensus. This document specifies the technical architecture for implementing the consensus engine that coordinates track selection across an unlimited number of nodes.

**Core Architecture:**
- 🎯 **Unified Consensus Model**: Single hierarchical architecture scales from 2 to 1,000,000+ nodes
- 🌐 **GossipSub PubSub**: Production-grade IPFS libp2p messaging (O(log n) complexity)
- 🔒 **Byzantine Fault Tolerant**: Deterministic consensus resistant to malicious nodes (<33% adversary tolerance)
- 🛡️ **Node Integrity Verification**: Reproducible builds with cryptographic attestation to detect tampered nodes
- � **Content-Addressed Streaming**: IPFS-native track distribution with automatic deduplication
- ⚡ **Zero Configuration**: Automatic cluster formation via Kademlia DHT proximity routing

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Current Infrastructure](#current-infrastructure)
3. [Consensus Engine Components](#consensus-engine-components)
4. [Node Integrity Verification](#node-integrity-verification)
5. [Network Communication Layer](#network-communication-layer)
6. [Deterministic Track Selection](#deterministic-track-selection)
7. [State Management](#state-management)
8. [Integration Architecture](#integration-architecture)
9. [Performance Specifications](#performance-specifications)
10. [Implementation Requirements](#implementation-requirements)

---

## System Architecture

### Unified Hierarchical Consensus Model

Sleetbubble uses a **single adaptive consensus architecture** that automatically scales based on network size without requiring manual configuration or deployment changes:

```
┌─────────────────────────────────────────────────────────────┐
│                     GLOBAL CONSENSUS LAYER                  │
│                                                              │
│  Auto-elects beacon nodes based on:                        │
│  • Network uptime and stability                            │
│  • DHT proximity to network center                         │
│  • Consensus participation history                         │
│                                                              │
│  Responsibilities:                                          │
│  • Aggregate regional winners when network > 5000 nodes   │
│  • Publish canonical global queue (5 tracks)              │
│  • Coordinate cross-cluster handoffs                       │
│  • Maintain network health metrics                         │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ GossipSub: Regional Winners
                            │
┌─────────────────────────────────────────────────────────────┐
│                   REGIONAL CONSENSUS LAYER                  │
│                                                              │
│  Auto-formed clusters when network > 50 nodes:             │
│  • DHT Kademlia proximity grouping                         │
│  • Network latency-based clustering                        │
│  • Each region: 100-500 nodes                              │
│                                                              │
│  Delegate Election (per region):                           │
│  • Deterministic rotation based on slot number             │
│  • 3-5 delegates per region participate in global layer   │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ GossipSub: Cluster Winners
                            │
┌─────────────────────────────────────────────────────────────┐
│                    LOCAL CONSENSUS LAYER                    │
│                                                              │
│  Direct participation (always active):                      │
│  • All nodes subscribe to cluster topic                    │
│  • Propose tracks from personal library                    │
│  • Run deterministic selection algorithm locally           │
│  • Elect delegate to represent cluster in regional layer  │
│                                                              │
│  Cluster Formation (50-200 nodes each):                    │
│  • Automatic via DHT rendezvous protocol                   │
│  • Self-balancing when size limits exceeded                │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ GossipSub: Track Proposals
                            │
┌─────────────────────────────────────────────────────────────┐
│                      INDIVIDUAL NODES                       │
│                                                              │
│  Each node:                                                 │
│  • Processes audio library to HLS segments + IPFS pins    │
│  • Proposes tracks from personal catalog                   │
│  • Fetches winning consensus tracks via IPFS              │
│  • Streams via Liquidsoap HLS output                       │
│  • Publishes stream to IPNS for external access           │
└─────────────────────────────────────────────────────────────┘
```

### Automatic Layer Activation

The consensus engine automatically activates layers based on real-time network metrics:

| Network Size | Active Layers | Primary Topic | Consensus Latency | Architecture Mode |
|--------------|---------------|---------------|-------------------|-------------------|
| 2-49 nodes | Local only | `sleetbubble-consensus` | ~100-200ms | Flat P2P |
| 50-4,999 nodes | Local + Regional | `sleetbubble-region-{hash}` | ~300-500ms | Clustered |
| 5,000+ nodes | Local + Regional + Global | `sleetbubble-beacon` | ~800-1500ms | Hierarchical |

**Key Principle:** The architecture is designed once and adapts automatically. No staged rollout or manual configuration required.

---

## Current Infrastructure

Sleetbubble currently implements IPFS-based HLS streaming with the following operational components:

### Existing Services (src/)

```
ipfs/                    ← IPFS node with GossipSub configuration
setup/                   ← Initial configuration and music library processing
liquidsoap/              ← Audio streaming engine (radio.liq + HLS output)
hls-uploader/            ← Uploads HLS segments to IPFS, tracks CIDs
playlist-generator/      ← Generates IPFS playlists, publishes to IPNS
state-sync/              ← PubSub state synchronization (currently basic)
segment-cleanup/         ← Removes old HLS segments from local storage
config-page/             ← Web UI for stream access and configuration
```

### Data Flow (Current)

```
Audio Files (audio/trax/)
        ↓
[Setup Service] → Process playlist.config.json → Copy to /data/music/
        ↓
[Liquidsoap] → Read /data/music/playlist.m3u → Stream → HLS segments (/data/hls/)
        ↓
[HLS Uploader] → Monitor /data/hls/ → Pin segments to IPFS → Save CIDs (/data/state/ipfs_segments.json)
        ↓
[Playlist Generator] → Read ipfs_segments.json → Generate IPFS playlist → Publish IPNS → Update /data/state/stream_info.json
        ↓
[Config Page] → Serve player with IPNS playlist URL → External clients stream via IPFS gateway
```

### Current State Files

- `/data/state/ipfs_segments.json` - Maps local HLS segments to IPFS CIDs
- `/data/state/stream_info.json` - IPNS names and current stream metadata  
- `/data/state/current_position.json` - Liquidsoap playback position (unused for consensus currently)
- `/data/processed/` - Directory for pre-processed track segments (empty currently)

**Critical Gap:** No consensus mechanism exists. Each node streams independently from its own playlist. State-sync service exists but only broadcasts local state without coordinating global track selection.

---

## Consensus Engine Components

The consensus engine must be implemented as new services that integrate with the existing infrastructure. The following components form the complete consensus system:

### Component 1: Node Integrity Verifier

**Purpose:** Ensure all participating nodes run untampered code by verifying Docker image integrity.

**Location:** `src/integrity-verifier/`

**Technical Approach: Reproducible Builds + Remote Attestation**

Reproducible builds ensure that compiling the same source code produces bit-identical binaries, enabling cryptographic verification of running code [[1]](https://aws.amazon.com/blogs/web3/establishing-verifiable-security-reproducible-builds-and-aws-nitro-enclaves/).

```
Build Process                          Verification Process
─────────────                          ────────────────────

Source Code                            Node broadcasts:
   ↓                                   - Image SHA256
Dockerfile (pinned versions)           - Python package hashes
   ↓                                   - Service checksums
docker build --reproducible            
   ↓                                   Network verifies:
Docker Image                           - Image hash matches canonical
   ↓                                   - All dependencies unmodified
SHA256 Hash                            - Runtime memory integrity
   ↓
Canonical Hash Registry                Result:
(Published to IPFS)                    ✅ Node trusted (participates)
                                        ❌ Node tampered (flagged)
```

**Implementation Requirements:**

1. **Deterministic Dockerfile**
   - Pin all base image versions with digest hashes
   - Pin all Python package versions in requirements.txt
   - Use fixed timestamps for reproducibility
   - Disable layer caching that introduces non-determinism

2. **Runtime Attestation Service**
   - Calculate SHA256 of all Docker images at startup
   - Hash all Python source files in src/
   - Broadcast integrity manifest via IPFS PubSub
   - Monitor integrity of other nodes continuously

3. **Integrity Manifest Structure**
   ```json
   {
     "node_id": "QmNodeID...",
     "timestamp": 1699296000,
     "image_hashes": {
       "ipfs": "sha256:abc123...",
       "liquidsoap": "sha256:def456...",
       "consensus-engine": "sha256:ghi789..."
     },
     "source_hashes": {
       "src/consensus-engine/consensus.py": "sha256:...",
       "src/integrity-verifier/verifier.py": "sha256:..."
     },
     "canonical_release": "v2.0.0",
     "signature": "ed25519_signature"
   }
   ```

4. **Verification Logic**
   - Fetch canonical hashes from IPFS (published with each release)
   - Compare node's reported hashes against canonical
   - Track divergent nodes in `/data/state/integrity_tracking.json`
   - Broadcast tamper flag via PubSub topic `sleetbubble-integrity`

5. **Tamper Detection Responses**
   - **Flagged Node:** Excluded from consensus proposal aggregation
   - **Network Behavior:** Other nodes ignore proposals from flagged nodes
   - **Automatic Quarantine:** Flagged node cannot participate until fixed
   - **Self-Healing:** Node can rebuild from source and rejoin after re-verification

**Research Foundation:**
- Software-based attestation for distributed node compromise detection [[2]](https://mcn.cse.psu.edu/paper/yiyang/srds07.pdf)
- Reproducible builds as chain of trust for verification [[3]](https://medium.com/nttlabs/bit-for-bit-reproducible-builds-with-dockerfile-7cc2b9faed9f)
- Remote attestation for TEE integrity verification [[4]](https://oasis.net/blog/tees-remote-attestation-process)

---

### Component 2: Cluster Formation Manager

**Purpose:** Automatically organize nodes into optimal-size clusters using DHT proximity.

**Location:** `src/cluster-manager/`

**Technical Architecture:**

```
IPFS Kademlia DHT
       ↓
  Peer Discovery (sleetbubble-discovery topic)
       ↓
  Latency Measurement (IPFS ping)
       ↓
  Proximity Grouping (50-200 nodes per cluster)
       ↓
  Cluster Assignment (deterministic hash-based)
       ↓
  Delegate Election (rotates per consensus slot)
```

**Key Algorithms:**

1. **DHT Rendezvous Protocol**
   - Subscribe to discovery topic: `sleetbubble-discovery`
   - Broadcast heartbeat every 30 seconds with node metadata
   - Collect peer list via `ipfs dht findpeer`
   - Measure RTT latency to all discovered peers

2. **Cluster Assignment Algorithm**
   ```
   cluster_id = SHA256(node_id + nearest_peer_ids[:10]) % NUM_CLUSTERS
   
   If cluster size > 200:
     split_cluster() → create 2 new clusters
   
   If cluster size < 50 and adjacent cluster exists:
     merge_cluster() → combine with nearest cluster
   ```

3. **Delegate Election**
   ```
   slot_seed = SHA256(slot_number + cluster_id)
   delegate_index = slot_seed % cluster_size
   delegate = cluster_members[delegate_index]
   ```

**Data Structures:**

- `/data/state/cluster_info.json` - Current cluster membership and metadata
- `/data/state/cluster_topology.json` - Network-wide cluster map (learned via PubSub)

**Integration Points:**
- Reads peer list from IPFS DHT
- Publishes cluster formation events to `sleetbubble-discovery`
- Provides cluster membership to consensus engine

---

### Component 3: Track Catalog Processor

**Purpose:** Pre-process music library into HLS segments, pin to IPFS, generate catalog metadata.

**Location:** `src/catalog-processor/`

**Technical Process:**

```
Audio Library (/audio/trax/)
       ↓
[FFmpeg] → Transcode to AAC + segment to 6s chunks
       ↓
HLS Segments (.ts files) + Playlist (.m3u8)
       ↓
[IPFS Add] → Pin each segment → Collect CIDs
       ↓
Track Catalog Entry:
{
  "track_id": "sha256_of_original_file",
  "track_name": "song_title",
  "duration": 187,
  "segments": ["Qm...", "Qm...", "Qm..."],
  "m3u8_cid": "Qm...",
  "metadata": {"artist": "...", "album": "..."}
}
       ↓
Node Catalog: /data/state/node_catalog.json
{
  "node_id": "QmNodeID",
  "playlist_hash": "sha256(all_track_ids)",
  "track_count": 42,
  "tracks": [...]
}
```

**Key Requirements:**

1. **Deterministic Track IDs**
   - Use SHA256 of original audio file content (not filename)
   - Enables network-wide deduplication of identical tracks

2. **Pre-segmentation**
   - All tracks must be pre-segmented before consensus participation
   - Segments pinned permanently to local IPFS node
   - Remote nodes fetch segments via IPFS routing (DHT + Bitswap)

3. **Catalog Broadcasting**
   - Publish catalog summary to `sleetbubble-discovery` on startup
   - Other nodes learn network track availability
   - Consensus proposals reference track_id from catalog

**FFmpeg Processing:**
```bash
ffmpeg -i input.mp3 \
  -c:a aac -b:a 192k -ar 44100 \
  -f hls -hls_time 6 -hls_list_size 0 \
  -hls_segment_type mpegts \
  -hls_segment_filename "track_${TRACK_ID}_%03d.ts" \
  output.m3u8
```

---

### Component 4: Consensus Coordinator

**Purpose:** Core consensus engine that coordinates multi-layer track selection.

**Location:** `src/consensus-engine/`

**Architecture:**

```
                    ┌─────────────────────┐
                    │  Consensus Scheduler │
                    │  (Slot Timing)       │
                    └──────────┬───────────┘
                               │
           ┌───────────────────┼───────────────────┐
           │                   │                   │
    ┌──────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐
    │   Proposal  │    │  Selection  │    │    Fetch    │
    │   Manager   │    │  Calculator │    │   Manager   │
    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
           │                   │                   │
           │                   │                   │
    ┌──────▼──────────────────▼───────────────────▼──────┐
    │           GossipSub PubSub Interface                │
    │  (sleetbubble-cluster-*, sleetbubble-region-*,     │
    │   sleetbubble-beacon, sleetbubble-integrity)       │
    └─────────────────────────────────────────────────────┘
```

**Consensus Phases (per slot):**

```
Slot Timeline (30 seconds):

t=0s    PROPOSE    All nodes broadcast track proposals to cluster topic
         ↓
t=10s   SELECT     Deterministic algorithm calculates winner from all proposals
         ↓
t=15s   AGGREGATE  Delegates forward cluster winners to regional topic
         ↓
t=20s   GLOBAL     Beacon nodes calculate global winner (if hierarchical mode)
         ↓
t=25s   FETCH      All nodes begin fetching winning track segments from IPFS
         ↓
t=30s   QUEUE      Track added to Liquidsoap queue, next slot begins
```

**Proposal Message Structure:**
```json
{
  "type": "TRACK_PROPOSAL",
  "slot": 12345,
  "node_id": "QmNodeID",
  "cluster_id": "cluster-abc123",
  "region_id": "region-def456",
  "track_id": "sha256:track_hash",
  "track_name": "Song Title",
  "duration": 187,
  "segments": ["QmSeg1", "QmSeg2", "..."],
  "catalog_hash": "sha256:node_catalog",
  "timestamp": 1699296000,
  "signature": "ed25519_signature"
}
```

**Deterministic Selection Algorithm:**

```python
def calculate_consensus_winner(proposals: List[Proposal], slot: int) -> Proposal:
    """
    Byzantine Fault Tolerant deterministic selection.
    All honest nodes independently calculate identical result.
    """
    valid_proposals = [p for p in proposals if verify_integrity(p.node_id)]
    
    if not valid_proposals:
        return fallback_track()
    
    proposal_hashes = sorted([p.track_id for p in valid_proposals])
    
    seed = f"{slot}:{':'.join(proposal_hashes)}"
    
    selection_hash = hashlib.sha256(seed.encode()).hexdigest()
    
    winner_index = int(selection_hash, 16) % len(valid_proposals)
    
    return valid_proposals[winner_index]
```

**Properties:**
- **Deterministic:** Identical inputs produce identical output on all nodes
- **Fair:** Each proposal has equal probability 1/N of selection
- **Unbiasable:** Winner cannot be predicted without knowing all proposals
- **Byzantine Resistant:** Malicious nodes cannot influence outcome beyond their proposals
- **No Coordination:** Nodes independently arrive at same winner without communication after proposal phase

**Research Foundation:**
- BFT consensus requires deterministic state machines for safety [[5]](https://arxiv.org/html/2204.03181v3)
- Cryptographic sortition for fair random selection [[6]](https://dl.acm.org/doi/10.1145/3636553)

---

### Component 5: IPFS Segment Fetcher

**Purpose:** Fetch winning track segments from IPFS network and prepare for Liquidsoap playback.

**Location:** `src/segment-fetcher/`

**Fetch Pipeline:**

```
Consensus Winner Announced
       ↓
Extract Segment CIDs from proposal
       ↓
[IPFS Bitswap] → Fetch segments in parallel
       ↓
[Verification] → Verify CID integrity (content addressing guarantees)
       ↓
[Local Cache] → Save to /data/consensus-tracks/{track_id}/
       ↓
[Liquidsoap Interface] → Add to playback queue
```

**Optimization Strategies:**

1. **Parallel Fetching**
   - Fetch all segments simultaneously (up to 30 concurrent requests)
   - 6-second segments × 187s track = ~31 segments
   - Target: Fetch complete track within 10-15 seconds

2. **Segment Verification**
   - IPFS content addressing automatically verifies integrity
   - CID = hash of content, tampering impossible without detection

3. **Caching Strategy**
   - Keep last 10 consensus tracks cached locally
   - Reuse segments if same track selected again (deduplication)
   - Cache shared across all nodes via IPFS DHT

4. **Fallback Handling**
   - If fetch fails: Use local library track as fallback
   - Broadcast divergence state to network
   - Auto-exclude from consensus temporarily until re-sync

**IPFS Fetch Implementation:**
```bash
for segment_cid in track_segments:
    ipfs cat $segment_cid > /data/consensus-tracks/${track_id}/${segment_cid}.ts &
done
wait
```

---

### Component 6: Queue Manager

**Purpose:** Maintain 5-track lookahead queue for seamless playback and consensus coordination.

**Location:** `src/queue-manager/`

**Queue Structure:**

```
┌─────────────────────────────────────┐
│  Track 0 (PLAYING NOW)              │  Liquidsoap currently streaming
├─────────────────────────────────────┤
│  Track 1 (NEXT)                     │  Fully fetched, ready to play
├─────────────────────────────────────┤
│  Track 2 (BUFFERED)                 │  Fetching segments
├─────────────────────────────────────┤
│  Track 3 (CONSENSUS COMPLETE)       │  Winner selected, awaiting fetch
├─────────────────────────────────────┤
│  Track 4 (PROPOSAL PHASE)           │  Proposals being collected
├─────────────────────────────────────┤
│  Track 5 (NEXT SLOT)                │  Not yet started
└─────────────────────────────────────┘

Timeline:
- Track 0 starts playing → Begin proposals for Track 5
- Track 0 at 50% complete → Select winner for Track 5
- Track 0 at 75% complete → Fetch segments for Track 5
- Track 1 begins playing → Track 5 moves to "CONSENSUS COMPLETE"
```

**Benefits:**
- **9-15 minutes buffer** for IPFS fetching even on slow connections
- **Survives network partitions** up to ~12 minutes
- **Allows convergence** if nodes temporarily disagree
- **Smooth transitions** even with high-latency IPFS routing

**Queue State File:** `/data/state/consensus_queue.json`

```json
{
  "current_slot": 12345,
  "queue": [
    {
      "slot": 12345,
      "track_id": "sha256:...",
      "track_name": "Current Track",
      "node_id": "QmOriginator",
      "status": "playing",
      "segments_path": "/data/consensus-tracks/sha256.../",
      "started_at": 1699296000
    },
    {
      "slot": 12346,
      "track_id": "sha256:...",
      "status": "ready",
      "fetch_complete": true
    },
    ...
  ],
  "updated_at": 1699296030
}
```

---

## Node Integrity Verification

### Technical Foundation: Reproducible Builds + Runtime Attestation

Byzantine Fault Tolerant consensus requires that the network can identify tampered nodes and exclude them from consensus participation. Sleetbubble implements this through **deterministic builds** combined with **continuous runtime attestation**.

### Reproducible Build System

**Objective:** Ensure all nodes running the same version produce bit-identical binaries.

**Docker Build Requirements:**

1. **Pin all base images with digest hashes**
   ```dockerfile
   FROM ipfs/kubo@sha256:abc123... AS ipfs
   FROM python:3.11-slim@sha256:def456... AS python-base
   FROM savonet/liquidsoap:v2.2.5@sha256:ghi789... AS liquidsoap
   ```

2. **Pin all Python dependencies**
   ```txt
   requests==2.31.0
   watchdog==3.0.0
   ```

3. **Disable non-deterministic layers**
   ```dockerfile
   ENV PYTHONDONTWRITEBYTECODE=1
   ENV PYTHONHASHSEED=0
   ENV SOURCE_DATE_EPOCH=1699296000
   ```

4. **Strip timestamps from compiled artifacts**
   ```bash
   find /app -name "*.pyc" -delete
   python3 -m compileall -b /app
   ```

### Integrity Manifest Generation

Each node generates cryptographic manifest at startup:

**File:** `src/integrity-verifier/generate-manifest.py`

```python
import hashlib
import json
import os
import subprocess
from pathlib import Path

def hash_file(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            sha256.update(chunk)
    return sha256.hexdigest()

def hash_directory(dirpath: Path, extensions: list) -> dict:
    hashes = {}
    for ext in extensions:
        for filepath in dirpath.rglob(f'*{ext}'):
            relative = filepath.relative_to(dirpath)
            hashes[str(relative)] = hash_file(filepath)
    return hashes

def get_docker_image_digest(image_name: str) -> str:
    result = subprocess.run(
        ['docker', 'inspect', '--format={{.Id}}', image_name],
        capture_output=True,
        text=True
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"

def generate_integrity_manifest():
    manifest = {
        "version": os.getenv('SLEETBUBBLE_VERSION', 'v2.0.0'),
        "node_id": os.getenv('NODE_ID'),
        "timestamp": int(time.time()),
        
        "docker_images": {
            "ipfs": get_docker_image_digest("sleetbubble-ipfs"),
            "consensus": get_docker_image_digest("sleetbubble-consensus"),
            "liquidsoap": get_docker_image_digest("sleetbubble-liquidsoap"),
        },
        
        "source_files": hash_directory(
            Path('/src'), 
            ['.py', '.sh', '.liq']
        ),
        
        "dependencies": hash_directory(
            Path('/usr/local/lib/python3.11/site-packages'),
            ['.py', '.so']
        ),
    }
    
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode()
    ).hexdigest()
    
    manifest['manifest_hash'] = manifest_hash
    
    return manifest
```

### Canonical Release Registry

Official releases publish canonical manifest to IPFS:

```bash
CANONICAL_MANIFEST_CID="Qm..." 

ipfs pin add $CANONICAL_MANIFEST_CID

echo $CANONICAL_MANIFEST_CID > /state/canonical_manifest_cid.txt
```

Nodes fetch canonical manifest on startup and compare against their own.

### Runtime Verification Service

**File:** `src/integrity-verifier/verify-network.py`

```python
import json
import requests
import time
from typing import Dict, Set

IPFS_API = 'http://ipfs:5001'
INTEGRITY_TOPIC = 'sleetbubble-integrity'

class IntegrityVerifier:
    def __init__(self, node_id: str, manifest: dict):
        self.node_id = node_id
        self.local_manifest = manifest
        self.canonical_manifest = self.fetch_canonical()
        self.verified_nodes: Set[str] = set()
        self.tampered_nodes: Set[str] = set()
        
    def fetch_canonical(self) -> dict:
        with open('/state/canonical_manifest_cid.txt', 'r') as f:
            cid = f.read().strip()
        
        response = requests.post(
            f'{IPFS_API}/api/v0/cat',
            params={'arg': cid}
        )
        
        return json.loads(response.text)
    
    def verify_self(self) -> bool:
        return (
            self.local_manifest['manifest_hash'] == 
            self.canonical_manifest['manifest_hash']
        )
    
    def broadcast_attestation(self):
        attestation = {
            "type": "INTEGRITY_ATTESTATION",
            "node_id": self.node_id,
            "manifest_hash": self.local_manifest['manifest_hash'],
            "version": self.local_manifest['version'],
            "timestamp": int(time.time())
        }
        
        requests.post(
            f'{IPFS_API}/api/v0/pubsub/pub',
            params={'arg': INTEGRITY_TOPIC},
            files={'data': json.dumps(attestation)}
        )
    
    def handle_attestation(self, attestation: dict):
        node_id = attestation['node_id']
        reported_hash = attestation['manifest_hash']
        canonical_hash = self.canonical_manifest['manifest_hash']
        
        if reported_hash == canonical_hash:
            self.verified_nodes.add(node_id)
            if node_id in self.tampered_nodes:
                self.tampered_nodes.remove(node_id)
                print(f"✅ Node {node_id} integrity restored")
        else:
            self.tampered_nodes.add(node_id)
            if node_id in self.verified_nodes:
                self.verified_nodes.remove(node_id)
            print(f"❌ Node {node_id} TAMPERED (hash mismatch)")
            
        self.save_integrity_state()
    
    def save_integrity_state(self):
        state = {
            "verified_nodes": list(self.verified_nodes),
            "tampered_nodes": list(self.tampered_nodes),
            "updated_at": int(time.time())
        }
        
        with open('/state/integrity_tracking.json', 'w') as f:
            json.dump(state, f, indent=2)
    
    def is_node_trusted(self, node_id: str) -> bool:
        return (
            node_id in self.verified_nodes and 
            node_id not in self.tampered_nodes
        )
```

### Consensus Integration

The consensus engine MUST filter proposals from untrusted nodes:

```python
def calculate_consensus_winner(proposals: List[Proposal], slot: int) -> Proposal:
    integrity_verifier = IntegrityVerifier.get_instance()
    
    trusted_proposals = [
        p for p in proposals 
        if integrity_verifier.is_node_trusted(p.node_id)
    ]
    
    if not trusted_proposals:
        return fallback_track()
    
    proposal_hashes = sorted([p.track_id for p in trusted_proposals])
    seed = f"{slot}:{':'.join(proposal_hashes)}"
    selection_hash = hashlib.sha256(seed.encode()).hexdigest()
    winner_index = int(selection_hash, 16) % len(trusted_proposals)
    
    return trusted_proposals[winner_index]
```

### State File: `/data/state/integrity_tracking.json`

```json
{
  "canonical_version": "v2.0.0",
  "canonical_manifest_cid": "QmCanonical...",
  "self_verified": true,
  "self_manifest_hash": "abc123...",
  "verified_nodes": [
    "QmNode1...",
    "QmNode2..."
  ],
  "tampered_nodes": [
    "QmBadNode..."
  ],
  "last_attestation_broadcast": 1699296000,
  "updated_at": 1699296000
}
```

**Research Foundation:**
- Software-based attestation detects tampered code in distributed systems [[7]](https://sceweb.uhcl.edu/yang/teaching/csci5931WSNfall2008/Soft%20Tamper%20Proofing_PIV.pdf)
- Reproducible builds enable cryptographic verification [[8]](https://aws.amazon.com/blogs/web3/establishing-verifiable-security-reproducible-builds-and-aws-nitro-enclaves/)
- Remote attestation mechanisms for node integrity [[9]](https://oasis.net/blog/tees-remote-attestation-process)

---

## Network Communication Layer

### GossipSub Configuration (CRITICAL)

IPFS must be configured with GossipSub for production-scale pubsub. The existing `src/ipfs/init-ipfs.sh` must be updated:

**File:** `src/ipfs/init-ipfs.sh`

```bash
#!/bin/bash

ipfs config --json API.HTTPHeaders.Access-Control-Allow-Origin '["*"]'
ipfs config --json API.HTTPHeaders.Access-Control-Allow-Methods '["GET", "POST", "PUT"]'

ipfs config Pubsub.Enabled true
ipfs config Pubsub.Router gossipsub

ipfs config --json Pubsub.GossipSubD 6
ipfs config --json Pubsub.GossipSubDlo 4
ipfs config --json Pubsub.GossipSubDhi 12
ipfs config --json Pubsub.GossipSubDlazy 6

ipfs config --json Pubsub.GossipSubHeartbeatInterval '"700ms"'
ipfs config --json Pubsub.GossipSubHistoryLength 5
ipfs config --json Pubsub.GossipSubHistoryGossip 3

ipfs config --json Swarm.ConnMgr.LowWater 100
ipfs config --json Swarm.ConnMgr.HighWater 500
ipfs config --json Swarm.ConnMgr.GracePeriod '"60s"'

ipfs config --json Routing.Type '"dhtclient"'
ipfs config --json Routing.AcceleratedDHTClient true

ipfs config --json Datastore.StorageMax '"50GB"'
ipfs config --json Datastore.GCPeriod '"1h"'

echo "✅ IPFS configured for decentralized consensus"
```

**Performance Characteristics:**

| Metric | FloodSub (Old) | GossipSub (Required) |
|--------|----------------|----------------------|
| Message Propagation | O(n²) | O(log n) |
| Bandwidth/Node @ 1000 nodes | ~100 MB/s | ~100 KB/s |
| Latency @ 10,000 nodes | Fails | ~500ms |
| Max Supported Nodes | ~100 | 100,000+ |

### PubSub Topic Architecture

```
sleetbubble-discovery                     ← Node announcements, cluster formation
sleetbubble-integrity                     ← Integrity attestations
sleetbubble-consensus                     ← All consensus (if network < 50 nodes)

sleetbubble-cluster-{cluster_id}          ← Local cluster proposals (50-200 nodes)
sleetbubble-region-{region_id}            ← Regional aggregation (delegates only)
sleetbubble-beacon                        ← Global consensus (beacon nodes only)

sleetbubble-queue                         ← Global queue broadcasts
```

### Message Encoding

All PubSub messages use JSON with multibase encoding:

```python
import json
import base64

def encode_message(data: dict) -> str:
    json_bytes = json.dumps(data).encode('utf-8')
    base64_str = base64.urlsafe_b64encode(json_bytes).decode().rstrip('=')
    return 'u' + base64_str

def decode_message(multibase: str) -> dict:
    if not multibase.startswith('u'):
        raise ValueError("Invalid multibase encoding")
    
    base64_str = multibase[1:] + '=='
    json_bytes = base64.urlsafe_b64decode(base64_str)
    return json.loads(json_bytes.decode('utf-8'))
```

### Subscription Management

Each node subscribes to multiple topics simultaneously:

```python
def subscribe_all_topics():
    topics = [
        'sleetbubble-discovery',
        'sleetbubble-integrity',
        f'sleetbubble-cluster-{cluster_id}',
        'sleetbubble-queue'
    ]
    
    if is_delegate:
        topics.append(f'sleetbubble-region-{region_id}')
    
    if is_beacon:
        topics.append('sleetbubble-beacon')
    
    for topic in topics:
        subscribe_thread = threading.Thread(
            target=listen_to_topic,
            args=(topic,),
            daemon=True
        )
        subscribe_thread.start()
```

**Research Foundation:**
- GossipSub protocol specification and scalability proof [[10]](https://research.protocol.ai/blog/2019/a-new-lab-for-resilient-networks-research/PL-TechRep-gossipsub-v0.1-Dec30.pdf)
- Ethereum 2.0 uses GossipSub for 80,000+ validator coordination [[11]](https://www.youtube.com/watch?v=vveUuE7YlZ8)
- IPFS DHT + GossipSub architecture [[12]](https://arxiv.org/pdf/2207.06369)

---

## Deterministic Track Selection

### Byzantine Fault Tolerant Selection Algorithm

The core of sleetbubble consensus is a deterministic function that all nodes execute independently to arrive at the same winner:

```python
def calculate_consensus_winner(
    proposals: List[TrackProposal], 
    slot: int,
    integrity_verifier: IntegrityVerifier
) -> TrackProposal:
    """
    Deterministic Byzantine Fault Tolerant track selection.
    
    Properties:
    - All honest nodes calculate identical result
    - Fair: each proposal has equal probability 1/N
    - Unbiasable: winner unpredictable without all proposals
    - Tamper-resistant: excludes untrusted nodes
    - No coordination needed after proposal phase
    """
    
    trusted_proposals = [
        p for p in proposals 
        if integrity_verifier.is_node_trusted(p.node_id)
    ]
    
    if not trusted_proposals:
        logger.warning(f"No trusted proposals for slot {slot}")
        return generate_fallback_track()
    
    unique_proposals = remove_duplicates(trusted_proposals)
    
    sorted_hashes = sorted([p.track_id for p in unique_proposals])
    
    seed_string = f"{slot}:{':'.join(sorted_hashes)}"
    
    selection_hash = hashlib.sha256(seed_string.encode()).hexdigest()
    
    winner_index = int(selection_hash, 16) % len(unique_proposals)
    
    winner = unique_proposals[winner_index]
    
    logger.info(
        f"Consensus slot {slot}: {winner.track_name} "
        f"from {winner.node_id} ({len(unique_proposals)} proposals)"
    )
    
    return winner

def remove_duplicates(proposals: List[TrackProposal]) -> List[TrackProposal]:
    """
    Remove duplicate proposals from same node or same track.
    """
    seen_nodes = set()
    seen_tracks = set()
    unique = []
    
    for p in proposals:
        if p.node_id not in seen_nodes and p.track_id not in seen_tracks:
            unique.append(p)
            seen_nodes.add(p.node_id)
            seen_tracks.add(p.track_id)
    
    return unique

def generate_fallback_track() -> TrackProposal:
    """
    Generate fallback from local library if consensus fails.
    """
    local_catalog = load_catalog('/state/node_catalog.json')
    if not local_catalog['tracks']:
        return silence_track()
    
    track = local_catalog['tracks'][0]
    
    return TrackProposal(
        node_id=os.getenv('NODE_ID'),
        track_id=track['hash'],
        track_name=track['name'],
        duration=track['duration'],
        segments=track['segments'],
        is_fallback=True
    )
```

### Mathematical Proof of Fairness

Given N valid proposals with unique track IDs:

```
seed = f"{slot}:{track_id_1}:{track_id_2}:...:{track_id_N}"
hash = SHA256(seed) → 256-bit uniformly distributed output
index = hash mod N → uniformly distributed over [0, N-1]

Therefore: P(proposal_i wins) = 1/N for all i ∈ [0, N-1]
```

SHA256 properties guarantee:
- **Collision resistance:** Impossible to find two inputs with same hash
- **Uniform distribution:** Output bits statistically random
- **Determinism:** Same input always produces same output

### Consensus Slot Timing

Each consensus slot follows strict timing to ensure synchronization:

```
Slot Duration: 30 seconds
Network Scale: Adaptive based on size

Small Network (< 50 nodes):
├─ 0s:  All nodes propose
├─ 10s: All nodes select winner
├─ 15s: All nodes fetch segments
└─ 30s: Track added to queue, next slot starts

Large Network (> 5000 nodes):
├─ 0s:  All nodes propose to clusters
├─ 8s:  Cluster delegates aggregate to regions
├─ 16s: Regional delegates aggregate to beacon
├─ 20s: Beacon calculates global winner
├─ 22s: Global winner broadcast
├─ 25s: All nodes fetch segments
└─ 30s: Track queued, next slot starts
```

**Clock Synchronization:**
- Nodes use slot number (monotonic counter) not wall-clock time
- Slot advances when current track transition occurs
- Minor clock drift tolerated due to 5-track lookahead buffer

**Research Foundation:**
- Byzantine consensus determinism requirements [[13]](https://dl.acm.org/doi/10.1145/3636553)
- Cryptographic sortition for unbiased selection [[14]](https://arxiv.org/html/2204.03181v3)
- SHA256 collision resistance proof [[15]](https://eprint.iacr.org/2025/816.pdf)

---

## State Management

### State Files Architecture

All consensus and coordination state stored in `/data/state/`:

```
/data/state/
├── node_catalog.json              ← This node's music catalog
├── cluster_info.json              ← Current cluster membership
├── integrity_tracking.json        ← Network integrity verification status
├── consensus_queue.json           ← 5-track lookahead queue
├── proposals_{slot}.json          ← Proposals for specific slot
├── ipfs_segments.json             ← Live streaming segments (existing)
├── stream_info.json               ← IPNS publication info (existing)
└── current_position.json          ← Playback position (existing)
```

### State File Specifications

#### `node_catalog.json`
```json
{
  "node_id": "QmNodeID",
  "version": "v2.0.0",
  "playlist_hash": "sha256:abc123",
  "track_count": 42,
  "total_duration": 7890,
  "generated_at": 1699296000,
  "tracks": [
    {
      "track_id": "sha256:trackHash",
      "track_name": "Song Title",
      "artist": "Artist Name",
      "album": "Album Name",
      "duration": 187,
      "segments": ["QmSeg1", "QmSeg2", "QmSeg3", "..."],
      "segment_count": 31,
      "m3u8_cid": "QmPlaylist",
      "original_cid": "QmOriginal"
    }
  ]
}
```

#### `cluster_info.json`
```json
{
  "cluster_id": "cluster-abc123",
  "region_id": "region-def456",
  "joined_at": 1699296000,
  "is_delegate": false,
  "delegate_node": "QmDelegate",
  "members": [
    {
      "node_id": "QmNode1",
      "latency_ms": 45,
      "last_seen": 1699296000
    }
  ],
  "member_count": 127,
  "updated_at": 1699296000
}
```

#### `consensus_queue.json`
```json
{
  "current_slot": 12345,
  "network_mode": "hierarchical",
  "queue": [
    {
      "slot": 12345,
      "track_id": "sha256:...",
      "track_name": "Current Track",
      "source_node": "QmOriginator",
      "status": "playing",
      "segments_path": "/data/consensus-tracks/sha256.../",
      "started_at": 1699296000,
      "ends_at": 1699296187
    },
    {
      "slot": 12346,
      "track_id": "sha256:...",
      "status": "ready",
      "fetch_complete": true,
      "fetched_at": 1699296120
    },
    {
      "slot": 12347,
      "status": "fetching",
      "fetch_progress": "23/31 segments"
    },
    {
      "slot": 12348,
      "status": "consensus_complete",
      "winner_announced_at": 1699296150
    },
    {
      "slot": 12349,
      "status": "proposing",
      "proposal_count": 87
    }
  ],
  "updated_at": 1699296000
}
```

### State Synchronization

State files are:
- **Written:** By local services (consensus-engine, cluster-manager, integrity-verifier)
- **Read:** By other local services (liquidsoap-integration, segment-fetcher)
- **Not synchronized:** State files are node-local, coordination happens via PubSub

The existing `state-sync` service can be repurposed to monitor consensus queue for debugging.

---

## Integration Architecture

### Service Dependency Graph

```
                      ┌──────────┐
                      │   IPFS   │
                      └────┬─────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼────┐      ┌──────▼─────┐    ┌──────▼─────┐
   │ Setup   │      │ Integrity  │    │  Cluster   │
   │ Service │      │ Verifier   │    │  Manager   │
   └────┬────┘      └──────┬─────┘    └──────┬─────┘
        │                  │                  │
        │           ┌──────▼──────────────────▼─────┐
        │           │    Catalog Processor          │
        │           └──────┬────────────────────────┘
        │                  │
        │           ┌──────▼──────────────────┐
        │           │  Consensus Coordinator  │
        │           └──────┬──────────────────┘
        │                  │
        │           ┌──────▼──────┐  ┌─────────────┐
        │           │   Segment   │  │    Queue    │
        │           │   Fetcher   │  │   Manager   │
        │           └──────┬──────┘  └──────┬──────┘
        │                  │                 │
   ┌────▼──────────────────▼─────────────────▼──────┐
   │             Liquidsoap Engine                   │
   └────┬────────────────────────────────────────────┘
        │
   ┌────▼────────┐
   │ HLS Uploader│
   └────┬────────┘
        │
   ┌────▼──────────┐
   │   Playlist    │
   │  Generator    │
   └────┬──────────┘
        │
   ┌────▼──────────┐
   │  Config Page  │
   └───────────────┘
```

### Docker Compose Integration

Add new consensus services to existing `docker-compose.yml`:

```yaml
services:
  # ... existing services (ipfs, setup, liquidsoap, etc.) ...

  integrity-verifier:
    build:
      context: .
      dockerfile: src/integrity-verifier/Dockerfile
    container_name: sleetbubble-integrity
    depends_on:
      setup:
        condition: service_completed_successfully
      ipfs:
        condition: service_started
    volumes:
      - ./src:/src
      - ./data/state:/state
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - IPFS_API=http://ipfs:5001
      - NODE_ID=${NODE_ID:-node1}
      - SLEETBUBBLE_VERSION=v2.0.0
    restart: unless-stopped

  cluster-manager:
    build:
      context: .
      dockerfile: src/cluster-manager/Dockerfile
    container_name: sleetbubble-cluster
    depends_on:
      integrity-verifier:
        condition: service_started
    volumes:
      - ./data/state:/state
    environment:
      - IPFS_API=http://ipfs:5001
      - NODE_ID=${NODE_ID:-node1}
    restart: unless-stopped

  catalog-processor:
    build:
      context: .
      dockerfile: src/catalog-processor/Dockerfile
    container_name: sleetbubble-catalog
    depends_on:
      cluster-manager:
        condition: service_started
    volumes:
      - ./audio:/music
      - ./data/processed:/processed
      - ./data/state:/state
    environment:
      - IPFS_API=http://ipfs:5001
      - NODE_ID=${NODE_ID:-node1}
    restart: "no"

  consensus-engine:
    build:
      context: .
      dockerfile: src/consensus-engine/Dockerfile
    container_name: sleetbubble-consensus
    depends_on:
      catalog-processor:
        condition: service_completed_successfully
      cluster-manager:
        condition: service_started
    volumes:
      - ./data/state:/state
      - ./data/consensus-tracks:/consensus-tracks
    environment:
      - IPFS_API=http://ipfs:5001
      - NODE_ID=${NODE_ID:-node1}
    restart: unless-stopped

  segment-fetcher:
    build:
      context: .
      dockerfile: src/segment-fetcher/Dockerfile
    container_name: sleetbubble-fetcher
    depends_on:
      consensus-engine:
        condition: service_started
    volumes:
      - ./data/state:/state
      - ./data/consensus-tracks:/consensus-tracks
    environment:
      - IPFS_API=http://ipfs:5001
      - NODE_ID=${NODE_ID:-node1}
    restart: unless-stopped

  queue-manager:
    build:
      context: .
      dockerfile: src/queue-manager/Dockerfile
    container_name: sleetbubble-queue
    depends_on:
      segment-fetcher:
        condition: service_started
    volumes:
      - ./data/state:/state
      - ./data/consensus-tracks:/consensus-tracks
    environment:
      - IPFS_API=http://ipfs:5001
      - NODE_ID=${NODE_ID:-node1}
    restart: unless-stopped
```

### Liquidsoap Integration

Modify `src/liquidsoap/radio.liq` to read from consensus queue:

```liquidsoap
#!/usr/bin/liquidsoap

set("log.stdout", true)
set("log.level", 4)

node_id = getenv("NODE_ID")

def log_msg(msg) =
  print("[#{node_id}] #{msg}")
end

log_msg("Starting Consensus-Driven Radio")

consensus_queue_file = "/state/consensus_queue.json"
consensus_tracks_dir = "/consensus-tracks"

def read_next_track() =
  if file.exists(consensus_queue_file) then
    content = file.contents(consensus_queue_file)
    queue = of_json(default=[("queue", [[]])], content)
    tracks = list.assoc(default=[], "queue", queue)
    
    if list.length(tracks) > 0 then
      next_track = list.hd(default=[("status", "none")], tracks)
      status = list.assoc(default="none", "status", next_track)
      
      if status == "ready" then
        track_path = list.assoc(default="", "segments_path", next_track)
        m3u8_path = "#{track_path}/playlist.m3u8"
        
        if file.exists(m3u8_path) then
          log_msg("Loading consensus track: #{m3u8_path}")
          m3u8_path
        else
          ""
        end
      else
        ""
      end
    else
      ""
    end
  else
    ""
  end
end

def consensus_source() =
  request.dynamic(read_next_track)
end

music = consensus_source()
music = mksafe(music)

aac_stream = %ffmpeg(
  format="mpegts",
  codec="aac",
  channels=2,
  ar=44100,
  b="192k"
)

streams = [("stream", aac_stream)]

def segment_name(~position, ~extname, stream_name) =
  timestamp = int_of_float(time())
  duration = 6
  "#{stream_name}_#{duration}_#{timestamp}_#{position}.#{extname}"
end

streams_info = [
  ("stream", (200000, "mp4a.40.2", "ts"))
]

output.file.hls(
  playlist="live.m3u8",
  segment_duration=6.0,
  segments=20,
  segments_overhead=10,
  segment_name=segment_name,
  streams_info=streams_info,
  "/hls",
  streams,
  music
)

log_msg("Consensus-driven HLS streaming active")
```

---

## Performance Specifications

### Scalability Targets

| Metric | 2-49 Nodes | 50-4,999 Nodes | 5,000-100,000 Nodes | 100,000-1,000,000 Nodes |
|--------|------------|----------------|---------------------|-------------------------|
| **Consensus Latency** | 100-200ms | 300-500ms | 800-1500ms | 1500-3000ms |
| **Bandwidth/Node** | 50-100 KB/s | 100-200 KB/s | 200-300 KB/s | 300-400 KB/s |
| **Messages/Slot/Node** | 1-50 | 100-500 | 500-2000 | 2000-5000 |
| **Active Layers** | Local | Local + Regional | Local + Regional + Beacon | Full Hierarchy |
| **Storage/Node** | 10-50 GB | 10-50 GB | 10-50 GB | 10-50 GB |
| **IPFS Connections** | 10-50 | 50-100 | 100-500 | 500-1000 |

### Resource Requirements

**Minimum Node Specifications:**
- **CPU:** 2 cores @ 2.0 GHz
- **RAM:** 4 GB
- **Storage:** 50 GB SSD
- **Network:** 10 Mbps symmetric

**Recommended Node Specifications:**
- **CPU:** 4 cores @ 2.5 GHz
- **RAM:** 8 GB
- **Storage:** 100 GB SSD
- **Network:** 50 Mbps symmetric

### Network Performance Guarantees

✅ **Byzantine Fault Tolerance:** Network operates correctly with up to 33% malicious nodes  
✅ **Partition Tolerance:** Network recovers from temporary network splits up to 12 minutes  
✅ **No Single Point of Failure:** Any subset of nodes can continue operations  
✅ **Censorship Resistance:** No node can block content network-wide  
✅ **Self-Healing:** Automatic cluster rebalancing and fault recovery  
✅ **Linear Scaling:** Per-node cost remains constant as network grows  

---

## Implementation Plan

This plan divides the implementation into 8 development sessions, each designed to fit within a single coding session with testing and validation.

---

### SESSION 1: IPFS Foundation & Integrity Verifier
**Duration:** 4-6 hours  
**Scope:** Configure IPFS for production consensus, implement node integrity verification

#### Deliverables:

1. **Update GossipSub Configuration**
   - File: `src/ipfs/init-ipfs.sh`
   - Enable GossipSub with production parameters
   - Configure DHT for peer discovery
   - Set connection manager limits

2. **Implement Integrity Manifest Generator**
   - File: `src/integrity-verifier/generate-manifest.py`
   - Hash all source files in src/
   - Calculate Docker image digests
   - Generate integrity manifest JSON
   - Save to `/data/state/integrity_manifest.json`

3. **Implement Integrity Broadcast Service**
   - File: `src/integrity-verifier/broadcast-attestation.py`
   - Subscribe to `sleetbubble-integrity` topic
   - Broadcast local manifest every 60 seconds
   - Listen for other nodes' attestations

4. **Create Integrity Verifier**
   - File: `src/integrity-verifier/verify-network.py`
   - Fetch canonical manifest from IPFS
   - Compare node attestations against canonical
   - Maintain verified/tampered node lists
   - Save to `/data/state/integrity_tracking.json`

5. **Dockerfile with Reproducible Builds**
   - File: `src/integrity-verifier/Dockerfile`
   - Pin Python base image with digest
   - Set deterministic environment variables
   - Pin all dependencies with versions

6. **Update docker-compose.yml**
   - Add integrity-verifier service
   - Configure dependencies and volumes
   - Set environment variables

#### Testing:

```bash
# Start IPFS and integrity verifier
docker compose up ipfs integrity-verifier

# Verify GossipSub is enabled
docker exec sleetbubble-ipfs ipfs config Pubsub.Router

# Check integrity manifest generation
cat data/state/integrity_manifest.json

# Verify attestation broadcasting
docker logs sleetbubble-integrity | grep "ATTESTATION"

# Test tamper detection (modify a source file)
echo "# tampered" >> src/integrity-verifier/verify-network.py
docker compose restart integrity-verifier
# Should flag itself as tampered

# Restore original file
git checkout src/integrity-verifier/verify-network.py
docker compose restart integrity-verifier
# Should restore verified status
```

#### Success Criteria:
- ✅ IPFS configured with GossipSub
- ✅ Integrity manifest generated correctly
- ✅ Attestations broadcast every 60 seconds
- ✅ Tamper detection works (flags modified nodes)
- ✅ State files created in `/data/state/`

---

### SESSION 2: Cluster Formation Manager
**Duration:** 4-6 hours  
**Scope:** Automatic peer discovery and cluster organization

#### Deliverables:

1. **Peer Discovery Service**
   - File: `src/cluster-manager/peer-discovery.py`
   - Subscribe to `sleetbubble-discovery` topic
   - Broadcast heartbeat with node metadata every 30s
   - Collect peer list from IPFS DHT
   - Measure RTT latency to discovered peers
   - Save to `/data/state/peer_list.json`

2. **Cluster Formation Algorithm**
   - File: `src/cluster-manager/cluster-formation.py`
   - Group nodes by network latency (DHT proximity)
   - Assign cluster_id deterministically
   - Handle cluster splits (>200 nodes)
   - Handle cluster merges (<50 nodes)
   - Save to `/data/state/cluster_info.json`

3. **Delegate Election**
   - File: `src/cluster-manager/delegate-election.py`
   - Calculate delegate based on slot number
   - Rotate delegates deterministically
   - Broadcast delegate announcements

4. **Cluster Health Monitor**
   - File: `src/cluster-manager/health-monitor.py`
   - Monitor cluster size continuously
   - Trigger rebalancing when needed
   - Log cluster membership changes

5. **Dockerfile**
   - File: `src/cluster-manager/Dockerfile`
   - Reproducible build configuration
   - Pin dependencies

6. **Update docker-compose.yml**
   - Add cluster-manager service
   - Configure dependencies

#### Testing:

```bash
# Start cluster manager
docker compose up cluster-manager

# Verify peer discovery
docker logs sleetbubble-cluster | grep "Discovered"
cat data/state/peer_list.json

# Check cluster formation
cat data/state/cluster_info.json
# Should show cluster_id, member_count

# Test with 2 nodes (simulate)
# Node 1:
NODE_ID=node1 docker compose up cluster-manager

# Node 2 (different terminal):
NODE_ID=node2 docker compose up cluster-manager

# Both should discover each other and form cluster
cat data/state/cluster_info.json | grep member_count
# Should show 2 members

# Test delegate election
# Check logs for delegate announcements
docker logs sleetbubble-cluster | grep "DELEGATE"
```

#### Success Criteria:
- ✅ Nodes discover each other via DHT
- ✅ Cluster formed with cluster_id
- ✅ Latency measured between peers
- ✅ Delegate elected and announced
- ✅ Cluster info saved to state file

---

### SESSION 3: Catalog Processor
**Duration:** 5-7 hours  
**Scope:** Music library pre-processing, HLS segmentation, IPFS pinning

#### Deliverables:

1. **Music Library Scanner**
   - File: `src/catalog-processor/scan-library.py`
   - Scan `/music` for audio files
   - Calculate SHA256 hash of each file
   - Extract metadata (artist, album, duration)
   - Detect duplicates across nodes

2. **HLS Segmentation Service**
   - File: `src/catalog-processor/segment-audio.py`
   - Use FFmpeg to transcode to AAC
   - Generate 6-second HLS segments
   - Create .m3u8 playlist
   - Save to `/data/processed/track_{id}/`

3. **IPFS Pinning Service**
   - File: `src/catalog-processor/pin-segments.py`
   - Pin each segment to IPFS
   - Collect CIDs for all segments
   - Pin m3u8 playlist
   - Verify pinning successful

4. **Catalog Generator**
   - File: `src/catalog-processor/generate-catalog.py`
   - Combine all track metadata
   - Calculate playlist_hash
   - Create node_catalog.json
   - Broadcast catalog summary to network

5. **Dockerfile**
   - File: `src/catalog-processor/Dockerfile`
   - Include FFmpeg and FFprobe
   - Reproducible build

6. **Update docker-compose.yml**
   - Add catalog-processor service

#### Testing:

```bash
# Prepare test music
mkdir -p audio/trax
cp /path/to/test-songs/*.mp3 audio/trax/

# Run catalog processor
docker compose up catalog-processor

# Verify scanning
docker logs sleetbubble-catalog | grep "Found"
# Should show "Found X tracks"

# Check HLS segmentation
ls data/processed/track_000/
# Should see .ts segments and .m3u8 playlist

# Verify IPFS pinning
docker logs sleetbubble-catalog | grep "Pinned"
# Should show CIDs for each segment

# Check catalog generation
cat data/state/node_catalog.json
# Should show:
# - node_id
# - playlist_hash
# - track_count
# - tracks array with segments

# Verify segments accessible via IPFS
SEGMENT_CID=$(cat data/state/node_catalog.json | jq -r '.tracks[0].segments[0]')
docker exec sleetbubble-ipfs ipfs cat $SEGMENT_CID > test_segment.ts
file test_segment.ts
# Should show "MPEG transport stream"
```

#### Success Criteria:
- ✅ Music library scanned successfully
- ✅ Tracks segmented to HLS format
- ✅ All segments pinned to IPFS
- ✅ Catalog generated with track metadata
- ✅ Segments retrievable via CID

---

### SESSION 4: Consensus Engine - Local Layer
**Duration:** 6-8 hours  
**Scope:** Implement local cluster consensus with deterministic selection

#### Deliverables:

1. **Proposal Manager**
   - File: `src/consensus-engine/proposal-manager.py`
   - Read node catalog
   - Select random track for slot
   - Create TrackProposal message
   - Broadcast to cluster topic
   - Collect proposals from other nodes
   - Save to `/data/state/proposals_{slot}.json`

2. **Deterministic Selection Calculator**
   - File: `src/consensus-engine/selection-calculator.py`
   - Filter proposals from verified nodes only
   - Remove duplicate proposals
   - Sort proposal hashes
   - Calculate SHA256(slot:hashes)
   - Select winner with hash % N
   - Verify determinism with unit tests

3. **Consensus Coordinator**
   - File: `src/consensus-engine/consensus-coordinator.py`
   - Manage consensus slot timing (30 seconds)
   - Coordinate proposal phase (0-10s)
   - Execute selection phase (10-15s)
   - Trigger fetch phase (15-25s)
   - Update consensus queue
   - Save to `/data/state/consensus_queue.json`

4. **PubSub Message Handler**
   - File: `src/consensus-engine/pubsub-handler.py`
   - Subscribe to cluster topic
   - Decode messages (multibase)
   - Route to proposal manager
   - Broadcast selection results

5. **Unit Tests**
   - File: `src/consensus-engine/test_selection.py`
   - Test deterministic selection algorithm
   - Test duplicate removal
   - Test integrity filtering
   - Test fairness (equal probability)

6. **Dockerfile and docker-compose.yml update**

#### Testing:

```bash
# Start consensus engine (single node)
docker compose up consensus-engine

# Verify proposal broadcasting
docker logs sleetbubble-consensus | grep "PROPOSAL"
# Should see proposals every 30 seconds

# Check consensus queue
cat data/state/consensus_queue.json
# Should show current_slot and queue

# Test deterministic selection (unit tests)
docker exec sleetbubble-consensus python3 -m pytest /src/consensus-engine/test_selection.py -v

# Simulate 2-node consensus
# Node 1:
NODE_ID=node1 docker compose up consensus-engine

# Node 2 (different terminal):
NODE_ID=node2 docker compose up consensus-engine

# Both should:
# - Propose tracks
# - Receive each other's proposals
# - Calculate SAME winner
# - Update consensus queue identically

# Verify both nodes agree on winner
diff <(docker exec node1-consensus cat /state/consensus_queue.json | jq '.queue[0].track_id') \
     <(docker exec node2-consensus cat /state/consensus_queue.json | jq '.queue[0].track_id')
# Should show no difference

# Test integrity filtering (tampered node)
# Modify node2 source code
docker exec node2-consensus sh -c "echo '# hack' >> /src/consensus-engine/consensus-coordinator.py"
docker compose restart node2-consensus
# Node2 should be flagged as tampered
# Node1 should ignore node2 proposals
docker logs node1-consensus | grep "ignored"
```

#### Success Criteria:
- ✅ Proposals broadcast every 30 seconds
- ✅ Multiple nodes receive proposals
- ✅ Deterministic selection produces identical results
- ✅ Unit tests pass (100% coverage)
- ✅ Tampered nodes excluded from selection
- ✅ Consensus queue updated correctly

---

### SESSION 5: Segment Fetcher & Queue Manager
**Duration:** 5-7 hours  
**Scope:** IPFS segment fetching and lookahead queue management

#### Deliverables:

1. **Segment Fetcher**
   - File: `src/segment-fetcher/fetch-segments.py`
   - Monitor consensus queue for tracks in "fetch" state
   - Extract segment CIDs from winning proposal
   - Fetch segments in parallel (30 concurrent)
   - Verify CID integrity
   - Save to `/data/consensus-tracks/{track_id}/`
   - Update track status to "ready"

2. **Fetch Progress Monitor**
   - File: `src/segment-fetcher/progress-monitor.py`
   - Track fetch progress (X/N segments)
   - Estimate time to completion
   - Handle fetch failures with retry
   - Update consensus queue with progress

3. **Queue Manager**
   - File: `src/queue-manager/queue-manager.py`
   - Maintain 5-track lookahead queue
   - Advance queue on track completion
   - Ensure queue never empty
   - Handle fallback if fetch fails
   - Save to `/data/state/consensus_queue.json`

4. **Fallback Handler**
   - File: `src/queue-manager/fallback-handler.py`
   - Select track from local catalog
   - Use when consensus fails or fetch times out
   - Broadcast divergence state
   - Auto-recovery when consensus resumes

5. **Dockerfiles and docker-compose.yml updates**

#### Testing:

```bash
# Start segment fetcher and queue manager
docker compose up segment-fetcher queue-manager

# Trigger consensus to generate winning track
docker compose up consensus-engine

# Monitor segment fetching
docker logs sleetbubble-fetcher -f | grep "Fetching"
# Should see parallel fetch of segments

# Check progress
cat data/state/consensus_queue.json | jq '.queue[0].fetch_progress'
# Should show "23/31 segments"

# Verify segments downloaded
ls data/consensus-tracks/sha256_*/
# Should see .ts files

# Wait for fetch completion
docker logs sleetbubble-fetcher | grep "Fetch complete"

# Check queue status
cat data/state/consensus_queue.json | jq '.queue[0].status'
# Should be "ready"

# Test 5-track lookahead
# Queue should always maintain 5 tracks:
cat data/state/consensus_queue.json | jq '.queue | length'
# Should output: 5

# Test fallback mechanism
# Stop IPFS temporarily to simulate fetch failure
docker compose stop ipfs
sleep 40
# Queue manager should use local track as fallback
cat data/state/consensus_queue.json | jq '.queue[0].is_fallback'
# Should be: true

# Restart IPFS
docker compose start ipfs
# Should recover to consensus tracks

# Test parallel fetching performance
# Measure time to fetch 30-segment track
time docker logs sleetbubble-fetcher | grep "Fetch complete"
# Should complete in <15 seconds on good connection
```

#### Success Criteria:
- ✅ Segments fetched from IPFS successfully
- ✅ Parallel fetching works (30 concurrent)
- ✅ Fetch progress tracked accurately
- ✅ Queue maintains 5 tracks always
- ✅ Fallback works when fetch fails
- ✅ Tracks transition: consensus→fetching→ready

---

### SESSION 6: Liquidsoap Integration
**Duration:** 4-6 hours  
**Scope:** Integrate consensus queue with Liquidsoap for playback

#### Deliverables:

1. **Queue Reader Script**
   - File: `src/liquidsoap/queue-reader.py`
   - Read `/data/state/consensus_queue.json`
   - Return path to next ready track
   - Generate m3u8 playlist for track segments
   - Handle track transitions

2. **Updated Liquidsoap Script**
   - File: `src/liquidsoap/radio.liq`
   - Replace static playlist with dynamic queue
   - Call queue-reader.py for next track
   - Handle track completion
   - Advance queue (call queue-manager)
   - Continue HLS output as before

3. **Track Completion Handler**
   - File: `src/liquidsoap/track-completed.py`
   - Triggered when track ends
   - Notify queue-manager to advance
   - Increment consensus slot
   - Trigger next proposal phase

4. **Update docker-compose.yml**
   - Configure liquidsoap dependencies

#### Testing:

```bash
# Ensure full pipeline running
docker compose up -d

# Verify Liquidsoap reads consensus queue
docker logs sleetbubble-liquidsoap | grep "consensus_queue"

# Check track loading
docker logs sleetbubble-liquidsoap | grep "Loading consensus track"
# Should show paths to consensus tracks

# Monitor HLS output
ls data/hls/
# Should see live.m3u8 and .ts segments

# Verify track playback
# Use VLC or ffplay to test stream
ffplay http://localhost:8080/ipfs/$(cat data/state/stream_info.json | jq -r .ipns_name)/live.m3u8

# Should play consensus tracks seamlessly

# Test track transitions
# Monitor queue advancement
watch -n 1 "cat data/state/consensus_queue.json | jq '.current_slot'"
# Should increment when track completes

# Verify consensus continues
# New proposals should be generated
docker logs sleetbubble-consensus | grep "Proposing slot"

# Test 2-node synchronized playback
# Both nodes should play same tracks in same order
# Node 1:
docker logs node1-liquidsoap | grep "Loading consensus track"

# Node 2:
docker logs node2-liquidsoap | grep "Loading consensus track"

# Compare track IDs - should match
```

#### Success Criteria:
- ✅ Liquidsoap reads from consensus queue
- ✅ Consensus tracks play successfully
- ✅ Track transitions seamless (no gaps)
- ✅ Queue advances on track completion
- ✅ New proposals triggered automatically
- ✅ Multiple nodes play synchronized

---

### SESSION 7: Multi-Layer Consensus (Regional + Beacon)
**Duration:** 6-8 hours  
**Scope:** Implement regional and beacon layers for large networks

#### Deliverables:

1. **Network Size Detector**
   - File: `src/consensus-engine/network-detector.py`
   - Monitor number of discovered peers
   - Determine active layer (local/regional/beacon)
   - Auto-activate layers based on thresholds
   - Update cluster info with layer status

2. **Regional Aggregator**
   - File: `src/consensus-engine/regional-aggregator.py`
   - Activate when network > 50 nodes
   - Collect cluster winners from delegates
   - Run deterministic selection on cluster winners
   - Broadcast regional winner to beacon

3. **Beacon Coordinator**
   - File: `src/consensus-engine/beacon-coordinator.py`
   - Activate when network > 5000 nodes
   - Collect regional winners
   - Run final deterministic selection
   - Broadcast global winner to all nodes

4. **Delegate Manager**
   - File: `src/consensus-engine/delegate-manager.py`
   - Determine if this node is delegate
   - Subscribe to regional topic if delegate
   - Forward cluster winner to region
   - Rotate delegate role per slot

5. **Topic Manager**
   - File: `src/consensus-engine/topic-manager.py`
   - Manage PubSub topic subscriptions
   - Subscribe to appropriate topics based on role
   - Handle topic switching on role change

6. **Update consensus-coordinator.py**
   - Integrate multi-layer logic
   - Route to appropriate layer based on size

#### Testing:

```bash
# Test automatic layer activation
# Single node (< 50 nodes)
docker compose up consensus-engine
docker logs sleetbubble-consensus | grep "Layer: LOCAL"
# Should show local-only mode

# Simulate 50+ nodes
# Set fake peer count for testing
docker exec sleetbubble-consensus sh -c "echo '75' > /tmp/mock_peer_count"
docker compose restart consensus-engine
docker logs sleetbubble-consensus | grep "Layer: REGIONAL"
# Should activate regional layer

# Test delegate election
cat data/state/cluster_info.json | jq '.is_delegate'
# Should show true/false based on slot

# Test regional aggregation
# When node is delegate:
docker logs sleetbubble-consensus | grep "REGIONAL_PROPOSAL"
# Should see cluster winner forwarded to region

# Simulate 5000+ nodes
docker exec sleetbubble-consensus sh -c "echo '5500' > /tmp/mock_peer_count"
docker compose restart consensus-engine
docker logs sleetbubble-consensus | grep "Layer: HIERARCHICAL"
# Should activate beacon layer

# Test beacon coordination
# Check for beacon winner broadcasts
docker logs sleetbubble-consensus | grep "GLOBAL_QUEUE_UPDATE"

# Verify all layers produce deterministic results
# Multiple nodes at each layer should agree
# Compare consensus_queue.json across nodes at same layer
```

#### Success Criteria:
- ✅ Layers activate automatically based on network size
- ✅ Regional aggregation works (50+ nodes)
- ✅ Beacon coordination works (5000+ nodes)
- ✅ Delegates elected and rotated correctly
- ✅ All layers produce identical consensus results
- ✅ Topic subscriptions managed correctly

---

### SESSION 8: Production Hardening & Testing
**Duration:** 6-8 hours  
**Scope:** Error handling, monitoring, end-to-end testing

#### Deliverables:

1. **Comprehensive Error Handling**
   - Files: All service files
   - Add try-catch blocks to all critical sections
   - Implement graceful degradation
   - Log errors with context
   - Automatic retry with exponential backoff

2. **Performance Metrics**
   - File: `src/monitoring/metrics-collector.py`
   - Track consensus latency
   - Monitor fetch times
   - Measure bandwidth usage
   - Track node participation rate
   - Save to `/data/state/metrics.json`

3. **Health Check Service**
   - File: `src/monitoring/health-check.py`
   - Check all services running
   - Verify IPFS connectivity
   - Monitor queue health
   - Detect stuck consensus
   - Expose HTTP endpoint for monitoring

4. **Network Partition Recovery**
   - File: `src/consensus-engine/partition-recovery.py`
   - Detect network partition
   - Switch to local catalog during partition
   - Re-sync consensus queue when recovered
   - Validate queue consistency

5. **Integration Test Suite**
   - File: `tests/integration/test_consensus_flow.py`
   - Test full consensus cycle
   - Test 2-node agreement
   - Test tampered node exclusion
   - Test network partition recovery
   - Test 24-hour sustained operation

6. **Load Test Suite**
   - File: `tests/load/test_scalability.py`
   - Simulate 100 nodes
   - Measure consensus latency
   - Test message propagation
   - Monitor resource usage

7. **Deployment Script**
   - File: `scripts/deploy-node.sh`
   - One-command node deployment
   - Automatic configuration
   - Health verification
   - Bootstrap to network

#### Testing:

```bash
# Run unit tests
docker compose run --rm consensus-engine python3 -m pytest /src/tests/unit/ -v

# Run integration tests
docker compose run --rm consensus-engine python3 -m pytest /src/tests/integration/ -v

# Test error recovery
# Kill IPFS mid-consensus
docker compose kill ipfs
# Services should handle gracefully
docker logs sleetbubble-consensus | grep "ERROR"
# Should show errors but no crashes

# Restart IPFS
docker compose start ipfs
# Services should reconnect automatically
docker logs sleetbubble-consensus | grep "Reconnected"

# Test network partition simulation
# Use iptables to block traffic between nodes
docker exec node1 iptables -A OUTPUT -d <node2_ip> -j DROP
# Wait 2 minutes
# Both nodes should use local fallback
cat node1/data/state/consensus_queue.json | jq '.queue[0].is_fallback'
# Should be true

# Restore connectivity
docker exec node1 iptables -D OUTPUT -d <node2_ip> -j DROP
# Nodes should re-sync and resume consensus

# Test 24-hour operation
docker compose up -d
# Wait 24 hours
docker ps
# All containers should still be running
docker logs sleetbubble-consensus | tail -100
# Should show recent consensus activity

# Check metrics
cat data/state/metrics.json | jq '.'
# Should show:
# - average_consensus_latency
# - total_tracks_played
# - network_participation_rate

# Test health check endpoint
curl http://localhost:5500/health
# Should return JSON with service status

# Load test (simulate 100 nodes)
cd tests/load
python3 simulate_100_nodes.py
# Should complete without errors
# Check metrics for latency under load

# Test deployment script
./scripts/deploy-node.sh --node-id node3 --bootstrap-peer /ip4/1.2.3.4/tcp/4001/p2p/QmPeer
# Should deploy new node and connect to network
docker ps | grep node3
# Should show all services running
```

#### Success Criteria:
- ✅ All unit tests pass (100% coverage)
- ✅ All integration tests pass
- ✅ Services recover from failures gracefully
- ✅ Network partition handled correctly
- ✅ 24-hour sustained operation successful
- ✅ Load tests show acceptable performance
- ✅ Metrics collected and accurate
- ✅ Health check endpoints working
- ✅ Deployment script works end-to-end

---

## Implementation Summary

### Total Development Time
- **Estimated:** 35-50 hours across 8 sessions
- **Team Size:** 1-2 developers

### Session Dependencies
```
SESSION 1 (IPFS + Integrity)
    ↓
SESSION 2 (Cluster Manager) ← Must complete Session 1
    ↓
SESSION 3 (Catalog Processor) ← Must complete Session 1
    ↓
SESSION 4 (Consensus Local) ← Must complete Sessions 1, 2, 3
    ↓
SESSION 5 (Fetcher + Queue) ← Must complete Session 4
    ↓
SESSION 6 (Liquidsoap) ← Must complete Session 5
    ↓
SESSION 7 (Multi-Layer) ← Must complete Session 6
    ↓
SESSION 8 (Production) ← Must complete all previous sessions
```

### Testing Strategy per Session
- **Unit Tests:** Written during implementation, run continuously
- **Integration Tests:** Run at end of each session
- **Regression Tests:** Run before starting next session
- **Load Tests:** Run only in Session 8

### Rollback Strategy
Each session is independent. If a session fails:
1. Rollback code changes for that session
2. Previous sessions remain functional
3. Debug and fix issues before proceeding
4. Re-run session tests until all pass

### Token Budget per Session
- **Average:** 100k-150k tokens per session
- **Peak:** 200k tokens (Session 4, Session 8)
- **Total:** ~1M tokens for complete implementation

This ensures all implementation work stays within a manageable scope and can be validated incrementally.

---

## Research References

### Distributed Systems & Consensus

[1] **Soft Tamper-Proofing via Program Integrity Verification**  
https://sceweb.uhcl.edu/yang/teaching/csci5931WSNfall2008/Soft%20Tamper%20Proofing_PIV.pdf  
*Software-based attestation for node compromise detection*

[2] **Distributed Software-based Attestation for Node Compromise Detection**  
https://mcn.cse.psu.edu/paper/yiyang/srds07.pdf  
*Distributed verification of code integrity in embedded systems*

[3] **Reproducible Builds with Dockerfile**  
https://medium.com/nttlabs/bit-for-bit-reproducible-builds-with-dockerfile-7cc2b9faed9f  
*Deterministic compilation for build verification*

[4] **Reproducible Builds and AWS Nitro Enclaves**  
https://aws.amazon.com/blogs/web3/establishing-verifiable-security-reproducible-builds-and-aws-nitro-enclaves/  
*Cryptographic attestation with reproducible builds*

[5] **A Comprehensive Review of BFT Consensus Algorithms**  
https://arxiv.org/html/2204.03181v3  
*Survey of Byzantine Fault Tolerant consensus mechanisms*

[6] **A Comprehensive Review of BFT Consensus Algorithms (ACM)**  
https://dl.acm.org/doi/10.1145/3636553  
*Academic review of BFT algorithm landscape*

### IPFS & P2P Networking

[7] **GossipSub: Attack-Resilient Message Propagation**  
https://research.protocol.ai/blog/2019/a-new-lab-for-resilient-networks-research/PL-TechRep-gossipsub-v0.1-Dec30.pdf  
*GossipSub protocol specification and scalability analysis*

[8] **Ethereum 2.0 GossipSub Implementation**  
https://www.youtube.com/watch?v=vveUuE7YlZ8  
*Production use of GossipSub for 80,000+ validators*

[9] **SmartPubSub: Content-based Pub-Sub on IPFS**  
https://arxiv.org/pdf/2207.06369  
*IPFS DHT + GossipSub architecture*

[10] **Remote Attestation for Trusted Execution Environments**  
https://oasis.net/blog/tees-remote-attestation-process  
*Remote attestation mechanisms for integrity verification*

[11] **libp2p Pubsub Peer Discovery with Kademlia DHT**  
https://medium.com/rahasak/libp2p-pubsub-peer-discovery-with-kademlia-dht-c8b131550ac7  
*DHT-based peer discovery for pubsub systems*

[12] **IPFS Content Addressing Explained**  
https://filebase.com/blog/ipfs-content-addressing-explained/  
*Content addressing and automatic deduplication*

### Cryptography & Security

[13] **Practical Byzantine Fault Tolerance**  
https://www.mdpi.com/2079-9292/12/18/3801  
*Survey of BFT consensus algorithms and improvements*

[14] **Deterministic Random Selection in Distributed Systems**  
https://eprint.iacr.org/2025/816.pdf  
*SHA256-based fair selection proof*

[15] **Byzantine Fault Tolerance in Blockchains**  
https://medium.com/blockchain-at-usc/the-fault-tolerant-consensus-problem-and-its-solutions-in-blockchains-and-distributed-systems-7f883227ebc7  
*Byzantine Generals Problem and consensus solutions*

---

## Conclusion

This technical specification provides a complete implementation guide for building the sleetbubble consensus engine. The architecture is:

- **Production-Ready:** Uses proven protocols (GossipSub, Kademlia DHT, BFT consensus)
- **Scalable:** Single architecture adapts from 2 to 1,000,000+ nodes
- **Secure:** Node integrity verification with reproducible builds
- **Decentralized:** No central authority, fully peer-to-peer
- **Byzantine Fault Tolerant:** Operates correctly with up to 33% malicious nodes

The existing IPFS streaming infrastructure provides the foundation. The consensus layer adds coordination without requiring architectural changes to the streaming components.

**Next Steps:**
1. Review this specification with the development team
2. Create implementation issues for each component
3. Begin Phase 1 implementation (Core Consensus Infrastructure)
4. Test with 2-10 node network
5. Iterate based on real-world performance
6. Scale to production with community testing

---

*Document Version: 2.0*  
*Last Updated: November 6, 2025*  
*License: MIT*

