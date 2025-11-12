# Consensus Engine Implementation Plan

## Architecture Overview

The consensus engine adds decentralized coordination to sleetbubble, allowing multiple nodes to agree on which playlist to stream. This creates horizontal scaling where all nodes serve the same content, providing redundancy and censorship resistance.

### Core Concepts

**Block-based Time**: Fixed 30-minute blocks. All nodes synchronize to wall-clock boundaries.

**Fixed Playlist Length**: Hardcoded minimum track duration (e.g., 60 minutes of content) ensures nodes can always fill a 30-minute block.

**Deterministic Selection**: Given a global index, all nodes run identical logic to select tracks. Hash verification prevents tampering.

**GossipSub Coordination**: Nodes broadcast proposals and votes over IPFS pubsub. Supermajority (67%) triggers consensus.

**Pin Management**: Only consensus-selected content gets pinned. Old blocks are unpinned (configurable retention).

## Component Architecture

```
src/consensus/
├── proposer.py          # Creates proposals for current block
├── pin_manager.py       # Pins/unpins content based on consensus
├── time_sync.py         # Block boundary calculations (enhanced with ntplib)
└── main.py              # Main consensus loop using PySyncObj
```

**Key Dependencies**:
- **PySyncObj**: Pure-Python Raft consensus library for voting/coordination (replaces custom gossip.py and coordinator.py)
- **ipfshttpclient**: IPFS HTTP API client for pubsub and pinning
- **ntplib**: NTP time synchronization for accurate block boundaries

## Technical Implementation Details

### 1. Time Synchronization (`time_sync.py`)

**Challenge**: All nodes must agree when blocks start/end despite network latency and clock drift.

**Solution**: Use UTC epoch math with NTP synchronization for accurate time.

```python
import time
import ntplib

BLOCK_DURATION_SECONDS = 1800
NTP_SERVER = 'pool.ntp.org'

def get_ntp_time():
    try:
        client = ntplib.NTPClient()
        response = client.request(NTP_SERVER, version=3, timeout=2)
        return response.tx_time
    except:
        return time.time()

def get_current_block_number():
    now = int(get_ntp_time())
    return now // BLOCK_DURATION_SECONDS

def get_block_start_time(block_num):
    return block_num * BLOCK_DURATION_SECONDS

def seconds_until_next_block():
    now = int(get_ntp_time())
    current_block_end = ((now // BLOCK_DURATION_SECONDS) + 1) * BLOCK_DURATION_SECONDS
    return current_block_end - now
```

**Key Points**:
- Block 0 = Unix epoch (1970-01-01 00:00:00)
- NTP sync eliminates clock drift issues (falls back to system time if NTP unavailable)
- All nodes calculate same block number at same moment (±1 second tolerance)
- Uses ntplib for sub-second accuracy

### 2. Playlist Analysis & Track Selection (`proposer.py`)

**Challenge**: Given a global index and local playlist, deterministically select complete tracks that fill 30 minutes.

**Solution**: Load manifest, calculate cumulative durations, add full tracks only. Reject if bounds exceeded.

```python
def select_tracks_for_block(manifest, global_index, block_duration=1800, overtime_threshold=30):
    tracks = manifest['tracks']
    total_tracks = len(tracks)
    
    # Calculate segment durations from manifest
    track_durations = []
    for track in tracks:
        segment_count = track['segment_count']
        duration_seconds = segment_count * 6  # 6s per segment
        track_durations.append(duration_seconds)
    
    # Start from global_index position (wrapped)
    start_idx = global_index % total_tracks
    
    selected_tracks = []
    accumulated_duration = 0
    idx = start_idx
    
    # Add complete tracks only, never slice
    while accumulated_duration < block_duration:
        track = tracks[idx]
        duration = track_durations[idx]
        
        # Check if adding this FULL track exceeds threshold
        potential_duration = accumulated_duration + duration
        
        if potential_duration > block_duration + overtime_threshold:
            # Adding this track would exceed bounds - stop
            break
        
        # Add the complete track
        selected_tracks.append(track)
        accumulated_duration += duration
        idx = (idx + 1) % total_tracks
    
    # Validate selection meets minimum duration (90% of block)
    if accumulated_duration < block_duration * 0.9:
        return None  # Reject proposal - not enough content
    
    # Validate doesn't exceed maximum
    if accumulated_duration > block_duration + overtime_threshold:
        return None  # Reject proposal - too much content
    
    return selected_tracks, accumulated_duration
```

**Key Principle**: Never slice tracks. Either include complete track or reject proposal. This ensures audio integrity and simplifies logic.

### 3. Proposal Creation (`proposer.py`)

**Challenge**: Create tamper-proof proposals that others can verify.

**Solution**: Hash all proposal components (playlist IPNS, track CIDs, metadata).

```python
def create_proposal(block_number, selected_tracks, node_id, ipns_key):
    # Gather all segment CIDs
    segment_cids = []
    for track in selected_tracks:
        segment_cids.extend([seg['cid'] for seg in track['segments']])
    
    proposal_data = {
        'block_number': block_number,
        'node_id': node_id,
        'ipns': ipns_key,
        'track_count': len(selected_tracks),
        'segment_count': len(segment_cids),
        'segment_cids': segment_cids,
        'timestamp': int(time.time())
    }
    
    # Create deterministic hash
    proposal_bytes = json.dumps(proposal_data, sort_keys=True).encode()
    proposal_hash = hashlib.sha256(proposal_bytes).hexdigest()
    
    proposal_data['hash'] = proposal_hash
    return proposal_data
```

**Hash Properties**:
- Deterministic: Same input always produces same hash
- Tamper-evident: Changing any field invalidates hash
- Verifiable: Other nodes can recompute and check

### 4. Consensus Coordination with PySyncObj

**Challenge**: Collect proposals from all nodes, determine winner, prevent split-brain.

**Solution**: Use PySyncObj (Raft-based consensus) instead of custom gossip/voting logic.

```python
from pysyncobj import SyncObj, replicated

class ConsensusState(SyncObj):
    def __init__(self, self_address, partner_addresses):
        super(ConsensusState, self).__init__(self_address, partner_addresses)
        self.proposals = {}
        self.current_winner = None
        self.current_block = 0
    
    @replicated
    def submit_proposal(self, block_number, proposal_data):
        if block_number not in self.proposals:
            self.proposals[block_number] = []
        self.proposals[block_number].append(proposal_data)
        return True
    
    @replicated
    def select_winner(self, block_number):
        if block_number not in self.proposals:
            return None
        
        proposals = self.proposals[block_number]
        if not proposals:
            return None
        
        seed = hashlib.sha256(str(block_number).encode()).hexdigest()
        
        def sort_key(proposal):
            combined = seed + proposal['hash']
            return hashlib.sha256(combined.encode()).hexdigest()
        
        sorted_proposals = sorted(proposals, key=sort_key)
        self.current_winner = sorted_proposals[0]
        self.current_block = block_number
        
        return self.current_winner
    
    def get_current_winner(self):
        return self.current_winner
```

**Benefits over custom implementation**:
- Raft consensus handles leader election, log replication, and fault tolerance automatically
- Split-brain prevention built-in (requires majority quorum)
- Production-ready with 10+ years of battle-testing
- Eliminates need for custom gossip.py and coordinator.py (~500 lines of code saved)
- Automatic node discovery and reconnection
- Configurable quorum thresholds

### 5. Pin Management (`pin_manager.py`)

**Challenge**: Pin only consensus-selected content, manage storage, handle cleanup.

**Solution**: Track pinned blocks, implement configurable retention.

```python
class PinManager:
    def __init__(self, ipfs_api, state_dir, blocks_to_keep=3):
        self.ipfs = ipfshttpclient.connect(ipfs_api)
        self.state_file = os.path.join(state_dir, 'pin_state.json')
        self.blocks_to_keep = blocks_to_keep
        self.pinned_blocks = self.load_state()
    
    def pin_consensus_winner(self, block_number, segment_cids):
        """Pin all segments from winning proposal"""
        for cid in segment_cids:
            try:
                self.ipfs.pin.add(cid)
            except Exception as e:
                logger.error(f"Failed to pin {cid}: {e}")
        
        # Track this block
        self.pinned_blocks.append({
            'block_number': block_number,
            'segment_cids': segment_cids,
            'pinned_at': int(time.time())
        })
        
        self.save_state()
        self.cleanup_old_blocks()
    
    def cleanup_old_blocks(self):
        """Unpin blocks outside retention window"""
        if len(self.pinned_blocks) <= self.blocks_to_keep:
            return
        
        # Sort by block number
        self.pinned_blocks.sort(key=lambda x: x['block_number'])
        
        # Remove oldest
        while len(self.pinned_blocks) > self.blocks_to_keep:
            old_block = self.pinned_blocks.pop(0)
            for cid in old_block['segment_cids']:
                try:
                    self.ipfs.pin.rm(cid)
                except Exception as e:
                    logger.warning(f"Failed to unpin {cid}: {e}")
```

**Retention Strategy**:
- Keep last N blocks (configurable: 3-10)
- Oldest blocks unpinned first (FIFO)
- Graceful failure (log errors, continue)

### 6. Setup Service Integration

**Change**: Remove pinning from setup, only prepare content.

**Before**:
```python
# setup_processor.py - OLD
cid = self.upload_to_ipfs(segment_path)  # pins by default
```

**After**:
```python
# setup_processor.py - NEW
cid = self.upload_to_ipfs(segment_path, pin=False)  # no pin, just add
```

**Rationale**: Content gets pinned only when consensus selects it. Initial upload just makes it available to local node for proposal creation.

### 7. Streamer Service Integration

**Change**: Streamer switches playlist based on consensus decisions from PySyncObj.

```python
class SlidingWindowStreamer:
    def __init__(self, config, ipns_manager, consensus_state):
        self.consensus = consensus_state
        self.active_playlist = None
    
    def update_stream(self):
        winner = self.consensus.get_current_winner()
        
        if winner and winner != self.active_playlist:
            self.load_consensus_playlist(winner)
            self.active_playlist = winner
```

## Configuration Structure

### `consensus.config.json`
```json
{
  "block_duration_seconds": 1800,
  "playlist_min_duration_seconds": 3600,
  "overtime_threshold_seconds": 30,
  "pin_retention_blocks": 3,
  "proposal_timeout_seconds": 60,
  "ntp_server": "pool.ntp.org",
  "pysyncobj": {
    "partner_nodes": ["127.0.0.1:4321", "127.0.0.1:4322"],
    "self_address": "127.0.0.1:4321"
  }
}
```

### `requirements.txt` additions
```
pysyncobj==0.3.12
ipfshttpclient==0.8.0a2
ntplib==0.4.0
```

## Implementation Plan (Updated with External Libraries)

**Total Estimated Time: 3.5 hours** (down from 8 hours - 56% reduction)

**Time Savings Breakdown**:
- Phase 3 eliminated: PySyncObj replaces custom gossip/coordination (~2.5 hours saved)
- Phase 1 reduced: ntplib simplifies time sync (~0.5 hours saved)
- Phase 4 eliminated: Raft consensus built-in (~1.5 hours saved)

### Phase 1: Dependencies & Time Sync (0.5 hours, reduced from 1 hour)

**Goal**: Install dependencies and establish block boundaries with NTP sync.

**Step 1.1**: Add dependencies to requirements.txt
```bash
cat >> requirements.txt << 'EOF'
pysyncobj==0.3.12
ntplib==0.4.0
ipfshttpclient==0.8.0a2
EOF
```

**Step 1.2**: Create time sync module with NTP
```bash
mkdir -p src/consensus
touch src/consensus/time_sync.py
```

Implementation requirements:
- Import ntplib for time synchronization
- `get_ntp_time()` → returns NTP-synced time (fallback to system time)
- `BLOCK_DURATION_SECONDS = 1800` constant
- `get_current_block_number()` → returns int (ntp_time // 1800)
- `get_block_start_time(block_num)` → returns timestamp
- `seconds_until_next_block()` → returns remaining seconds

**Test independently**:
```bash
cat > test_timesync.py << 'EOF'
import sys
sys.path.insert(0, 'src/consensus')
from time_sync import get_current_block_number, seconds_until_next_block, get_ntp_time
import time

ntp_time = get_ntp_time()
system_time = time.time()
print(f"NTP time: {ntp_time}")
print(f"System time: {system_time}")
print(f"Drift: {abs(ntp_time - system_time):.3f} seconds")

block_num = get_current_block_number()
remaining = seconds_until_next_block()
print(f"Current block: {block_num}")
print(f"Seconds until next block: {remaining}")
assert 0 <= remaining < 1800, "Invalid remaining time"
print("✓ Time sync working with NTP")
EOF

python test_timesync.py
```

**Step 1.3**: Create consensus config
```bash
cat > consensus.config.json << 'EOF'
{
  "block_duration_seconds": 1800,
  "playlist_min_duration_seconds": 3600,
  "overtime_threshold_seconds": 30,
  "pin_retention_blocks": 3,
  "proposal_timeout_seconds": 60,
  "ntp_server": "pool.ntp.org",
  "pysyncobj": {
    "partner_nodes": [],
    "self_address": "127.0.0.1:4321"
  }
}
EOF
```

**Phase 1 Complete**: NTP-synced time calculations work, dependencies installed.

---

### Phase 2: Proposal Creation (1 hour, reduced from 1.5 hours)

**Goal**: Generate valid proposals from local manifest.

**Step 2.1**: Create proposer module
```bash
mkdir -p src/consensus
touch src/consensus/proposer.py
```

Implementation requirements:
- `load_manifest(processed_dir)` → reads manifest.json
- `select_tracks_for_block(manifest, global_index, block_duration, overtime_threshold)` → returns tracks or None
- `create_proposal(block_number, tracks, node_id)` → returns proposal dict with hash

**Test independently** (no IPFS needed):
```bash
# Create test script
cat > test_proposer.py << 'EOF'
import sys
import json
sys.path.insert(0, 'src/consensus')
from proposer import load_manifest, select_tracks_for_block, create_proposal

# Load actual manifest
manifest = load_manifest('data/processed')
print(f"Loaded {len(manifest['tracks'])} tracks")

# Test selection at different indices
for global_index in [0, 1, 2]:
    result = select_tracks_for_block(manifest, global_index, 1800, 30)
    if result:
        tracks, duration = result
        print(f"Index {global_index}: {len(tracks)} tracks, {duration}s duration")
        assert 1620 <= duration <= 1830, f"Duration out of bounds: {duration}"
    else:
        print(f"Index {global_index}: Rejected (invalid duration)")

# Test proposal creation
result = select_tracks_for_block(manifest, 0, 1800, 30)
if result:
    tracks, duration = result
    proposal = create_proposal(100, tracks, "test-node-1")
    print(f"Proposal hash: {proposal['hash']}")
    print(f"Track count: {proposal['track_count']}")
    print(f"Segment count: {proposal['segment_count']}")
    
    # Verify hash is deterministic
    proposal2 = create_proposal(100, tracks, "test-node-1")
    assert proposal['hash'] == proposal2['hash'], "Hash not deterministic!"
    print("✓ Proposal creation working")
else:
    print("✗ No valid tracks for block")
EOF

python test_proposer.py
```

**Expected output**:
- Shows selected tracks for each index
- Durations between 1620-1830 seconds (90%-102% of 1800s)
- Same input produces same hash

**Step 2.2**: Modify setup to not pin
```bash
# Edit src/setup/setup_processor.py
# Find upload_to_ipfs method, change pin parameter default to False
```

**Test independently**:
```bash
# Run setup and verify no pins created
docker compose up setup
docker exec sleetbubble-ipfs-node1 ipfs pin ls --type=recursive | wc -l
# Should show 0 or very few pins (only IPFS system pins)
```

**Phase 2 Complete**: Can create valid proposals, setup doesn't pin content.

---

### Phase 3: PySyncObj Consensus Integration (1 hour, replaces Phases 3-4)

**Goal**: Use PySyncObj for Raft-based consensus instead of building custom gossip/voting. This replaces the original Phase 3 (GossipSub) and Phase 4 (Coordinator), saving ~2.5 hours and ~500 lines of code.

**Step 3.1**: Create consensus state class
```bash
touch src/consensus/consensus_state.py
```

Implementation requirements:
- `ConsensusState(SyncObj)` class that extends PySyncObj
- `@replicated submit_proposal(block_number, proposal_data)` → submits proposal to Raft log
- `@replicated select_winner(block_number)` → deterministically selects winner from proposals
- `get_current_winner()` → returns current consensus winner
- State automatically replicated across all nodes via Raft

**Test independently** (single node first):
```bash
cat > test_pysyncobj.py << 'EOF'
import sys
sys.path.insert(0, 'src/consensus')
from consensus_state import ConsensusState
import time
import json

config = json.load(open('consensus.config.json'))
self_addr = config['pysyncobj']['self_address']

consensus = ConsensusState(self_addr, [])

test_proposal = {
    "block_number": 100,
    "node_id": "test-node",
    "hash": "abc123",
    "segment_cids": ["cid1", "cid2"]
}

print("Submitting proposal...")
result = consensus.submit_proposal(100, test_proposal)
print(f"Submitted: {result}")

time.sleep(1)

print("Selecting winner...")
winner = consensus.select_winner(100)
print(f"Winner: {winner}")

assert winner is not None
assert winner['hash'] == 'abc123'
print("✓ PySyncObj consensus working")
EOF

python test_pysyncobj.py
```

**Expected output**:
- Proposal submitted to Raft log
- Winner selected deterministically
- State persisted in PySyncObj journal files

**Step 3.2**: Test with 2 nodes
```bash
cat > test_pysyncobj_multi.py << 'EOF'
import sys
sys.path.insert(0, 'src/consensus')
from consensus_state import ConsensusState
import time

node1 = ConsensusState('127.0.0.1:4321', ['127.0.0.1:4322'])
node2 = ConsensusState('127.0.0.1:4322', ['127.0.0.1:4321'])

time.sleep(2)

proposal1 = {"block_number": 100, "node_id": "node1", "hash": "hash-A", "segment_cids": []}
proposal2 = {"block_number": 100, "node_id": "node2", "hash": "hash-B", "segment_cids": []}

node1.submit_proposal(100, proposal1)
node2.submit_proposal(100, proposal2)

time.sleep(2)

winner1 = node1.select_winner(100)
winner2 = node2.select_winner(100)

print(f"Node 1 winner: {winner1['hash']}")
print(f"Node 2 winner: {winner2['hash']}")

assert winner1['hash'] == winner2['hash'], "Consensus mismatch!"
print("✓ Multi-node consensus working - both nodes agree on same winner")
EOF

python test_pysyncobj_multi.py
```

**Expected output**:
- Both nodes see same proposals (Raft replication)
- Both nodes select same winner (deterministic selection)
- Raft handles all network communication, retries, and consistency

**Phase 3 Complete**: PySyncObj handles all consensus coordination, replacing custom gossip and voting logic.

---

### Phase 4: Pin Management (0.5 hours, reduced from 1 hour)

**Goal**: Pin/unpin content based on consensus decisions. Simplified with ipfshttpclient batch operations.

**Step 4.1**: Create pin manager module
```bash
touch src/consensus/pin_manager.py
```

Implementation requirements:
- `PinManager(ipfs_api, state_dir, blocks_to_keep)` class
- `pin_consensus_winner(block_number, segment_cids)` → pins all CIDs
- `cleanup_old_blocks()` → unpins blocks outside retention window
- `load_state()` / `save_state()` → persist pin tracking

**Test independently**:
```bash
# Start IPFS
docker compose up -d ipfs

cat > test_pinmanager.py << 'EOF'
import sys
sys.path.insert(0, 'src/consensus')
from pin_manager import PinManager

pm = PinManager("http://localhost:5001", "data/state", blocks_to_keep=2)

# Pin fake CIDs for block 100
test_cids = [
    "QmPbvA2wgaJyDtRzCdnaU7ATHxymWyR7XHhixvt3VeDNFY",  # Real CID from manifest
    "QmSrWPKBxKXBK9i3jdowA3rHzXCYbFhYRa19vPSkpdSo36"
]

print("Pinning block 100...")
pm.pin_consensus_winner(100, test_cids)
print(f"✓ Pinned {len(test_cids)} CIDs")

# Verify pins exist
import ipfshttpclient
ipfs = ipfshttpclient.connect("/ip4/127.0.0.1/tcp/5001")
pins = ipfs.pin.ls(type='recursive')
pin_cids = [p['Cid'] for p in pins['Keys'].values()]
for cid in test_cids:
    assert cid in pin_cids, f"{cid} not pinned!"
print("✓ Pins verified in IPFS")

# Pin blocks 101, 102, 103 (should trigger cleanup of 100)
pm.pin_consensus_winner(101, ["Qm" + "a" * 44])
pm.pin_consensus_winner(102, ["Qm" + "b" * 44])
pm.pin_consensus_winner(103, ["Qm" + "c" * 44])

# Check block 100 was unpinned
print(f"Pinned blocks: {[b['block_number'] for b in pm.pinned_blocks]}")
assert 100 not in [b['block_number'] for b in pm.pinned_blocks]
print("✓ Cleanup working (block 100 removed)")
EOF

python test_pinmanager.py
```

**Expected output**:
- CIDs pinned successfully
- IPFS reports pins exist
- After pinning blocks 101-103, block 100 removed from tracking

**Verify cleanup in IPFS**:
```bash
docker exec sleetbubble-ipfs-node1 ipfs pin ls --type=recursive
# Should not show test_cids[0] and test_cids[1]
```

**Phase 4 Complete**: Pin operations work, cleanup triggers correctly with ipfshttpclient.

---

### Phase 5: Service Integration (1 hour, reduced from 1.5 hours)

**Goal**: Create consensus service using PySyncObj and integrate with docker-compose.

**Step 5.1**: Create consensus main loop
```bash
touch src/consensus/main.py
```

Implementation requirements:
- Load config, initialize ConsensusState (PySyncObj), pin_manager, proposer
- Main loop: wait for block boundary, create proposal, submit to PySyncObj, get winner, pin
- Graceful shutdown on SIGTERM
- PySyncObj handles all node communication automatically

**Test independently** (single container):
```bash
cat > src/consensus/Dockerfile << 'EOF'
FROM python:3.11-slim
RUN pip install pysyncobj ipfshttpclient ntplib
WORKDIR /app
COPY src/consensus/ /app/consensus/
COPY consensus.config.json /app/
CMD ["python", "-u", "consensus/main.py"]
EOF

docker compose up -d ipfs setup
docker compose up consensus
```

**Watch logs - should show**:
- NTP time sync successful
- Current block number
- Proposal created and submitted to PySyncObj
- PySyncObj Raft election (if multiple nodes)
- Winner selected
- Pin operations

**Step 5.2**: Test with 2 nodes
```bash
cat > docker-compose.consensus-test.yml << 'EOF'
version: '3.8'
services:
  consensus-node1:
    build: src/consensus
    environment:
      - NODE_ID=node-1
      - PYSYNCOBJ_ADDR=consensus-node1:4321
      - PYSYNCOBJ_PARTNERS=consensus-node2:4321
    networks:
      - sleetbubble
  
  consensus-node2:
    build: src/consensus
    environment:
      - NODE_ID=node-2
      - PYSYNCOBJ_ADDR=consensus-node2:4321
      - PYSYNCOBJ_PARTNERS=consensus-node1:4321
    networks:
      - sleetbubble

networks:
  sleetbubble:
EOF

docker compose -f docker-compose.consensus-test.yml up
```

**Watch both logs - should see**:
- Both nodes create proposals
- PySyncObj leader election (one becomes leader)
- Both nodes submit proposals to leader
- Leader replicates to follower
- Both nodes select same winner deterministically
- Both nodes pin same content

**Verify consensus**:
```bash
docker exec consensus-node1 cat /app/consensus_state.json
docker exec consensus-node2 cat /app/consensus_state.json
```

Both files should show same winner for each block.

**Phase 5 Complete**: PySyncObj-based consensus service runs, handles multi-node coordination.

---

### Phase 6: Multi-Node Testing & Validation (0.5 hours, reduced from 1 hour)
diff node1_pins.txt node2_pins.txt
# Should be identical (or very similar)

# Check consensus state files match
cat data/state/consensus_state.json  # node 1
# Compare with node 2's state file - winners should match
```

**Phase 6 Complete**: Consensus service runs, multiple nodes coordinate.

---

### Phase 7: Multi-Node Testing & Validation (1 hour)

**Goal**: Validate 3+ node network reaches consensus consistently.

**Step 7.1**: Deploy 3-node network
```bash
# Use docker compose override or manual NODE_ID changes
# Start 3 nodes with different playlists

# Node 1: original playlist
NODE_ID=node-1 docker compose up -d

# Node 2: modified playlist (swap track order in playlist.config.json)
NODE_ID=node-2 docker compose up -d

# Node 3: another variant
NODE_ID=node-3 docker compose up -d
```

**Test independently** (monitor consensus):
```bash
# Watch all logs simultaneously
docker compose logs -f consensus | grep "Consensus"

# Should see every ~30 minutes (per block):
# - 3 proposals broadcast
# - Supermajority reached (2+ nodes agree)
# - Winner announced
# - Pins updated
```

**Verify consensus over multiple blocks**:
```bash
cat > monitor_consensus.py << 'EOF'
import json
import time

# Monitor consensus state file
for i in range(5):  # Check 5 times over ~10 minutes
    try:
        state = json.load(open('data/state/consensus_state.json'))
        history = state.get('consensus_history', [])
        print(f"\n=== Check {i+1} ===")
        for entry in history[-3:]:  # Last 3 blocks
            print(f"Block {entry['block_number']}: Winner {entry['winner_hash']}")
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(120)  # Wait 2 minutes
EOF

python monitor_consensus.py
```

**Step 7.2**: Test failure scenarios

**Test node crash recovery**:
```bash
# Kill one node
docker compose stop consensus
sleep 30

# Restart it
docker compose up -d consensus

# Verify it rejoins consensus
docker compose logs consensus | tail -20
# Should show: "Loaded state", "Joined consensus", "Received proposals"
```

**Test network partition** (simulate):
```bash
# Disconnect node 3 from network
docker network disconnect sleet_test_default sleetbubble-consensus-node-3

# Wait 1 block
sleep 1900

# Nodes 1 and 2 should still reach consensus (2/3 = 67%)
docker compose logs consensus | grep "Supermajority"

# Reconnect node 3
docker network connect sleet_test_default sleetbubble-consensus-node-3

# Node 3 should catch up
```

**Step 7.3**: Validate pinning across network
```bash
# After consensus reached, check all nodes pinned same content
for node in node-1 node-2 node-3; do
  echo "=== $node ==="
  docker exec sleetbubble-ipfs-$node ipfs pin ls --type=recursive | wc -l
done

# All should show similar pin counts
```

**Final validation checklist**:
```bash
# Run this script to verify everything
cat > validate_consensus.sh << 'EOF'
#!/bin/bash
set -e

echo "1. Checking block sync..."
# All nodes should report same block number
# (Implementation: curl each node's status endpoint)

echo "2. Checking proposal broadcast..."
# Each node should have received proposals from others
grep "Received proposal from" data/state/consensus.log | wc -l

echo "3. Checking consensus history..."
# Should have N entries (N blocks elapsed)
cat data/state/consensus_state.json | jq '.consensus_history | length'

echo "4. Checking pin consistency..."
# All nodes should have similar pin counts
for node in node-1 node-2 node-3; do
  docker exec sleetbubble-ipfs-$node ipfs pin ls --type=recursive | wc -l
done

echo "5. Checking retention cleanup..."
# Old blocks should be unpinned
# (Check pin_state.json shows only recent N blocks)
cat data/state/pin_state.json | jq '.pinned_blocks | map(.block_number)'

echo "✓ All validation checks passed"
EOF

chmod +x validate_consensus.sh
./validate_consensus.sh
```

**Phase 7 Complete**: 3+ node network demonstrates:
- Block synchronization
- Proposal broadcast/receipt
- Supermajority consensus
- Deterministic winner selection
- Pin coordination
- Crash recovery
- Graceful degradation

## Docker Service Structure

### `src/consensus/Dockerfile`
```dockerfile
FROM python:3.11-slim

RUN pip install ipfshttpclient requests

WORKDIR /app
COPY src/consensus/ /app/consensus/
COPY src/utils/ /app/utils/

CMD ["python", "-u", "consensus/main.py"]
```

### `docker-compose.yml` addition
```yaml
consensus:
  build:
    context: .
    dockerfile: src/consensus/Dockerfile
  container_name: sleetbubble-consensus-${NODE_ID:-node1}
  depends_on:
    setup:
      condition: service_completed_successfully
    ipfs:
      condition: service_started
  volumes:
    - ./src:/app
    - ./data/state:/state
    - ./data/processed:/data/processed
    - ./consensus.config.json:/app/consensus.config.json:ro
  environment:
    - IPFS_API=http://ipfs:5001
    - STATE_DIR=/state
    - PROCESSED_DIR=/data/processed
    - NODE_ID=${NODE_ID:-node1}
    - CONSENSUS_CONFIG=/app/consensus.config.json
  restart: unless-stopped
```

## Key Design Decisions

**Separation of Concerns**: Each component has single responsibility (time sync, proposals, gossip, coordination, pinning).

**State Persistence**: All critical state saved to disk (pin state, consensus history, proposals).

**Graceful Degradation**: If consensus fails, node continues streaming local playlist.

**Configurability**: All magic numbers moved to config file.

**Idempotency**: Pin operations safe to retry, hash computations deterministic.

**Observability**: Extensive logging at each phase for debugging.

## Estimated Total Time: 8 hours

With smart planning and focus, this can be completed in 1-2 work days. Each phase builds on previous, allowing incremental testing and validation.

---

## Technology Research & Recommendations

### Critical Finding: Simplify with Existing Libraries

After extensive research into distributed consensus and P2P communication libraries, several production-ready solutions can significantly reduce development time and improve reliability:

### 1. **IPFS PubSub via ipfshttpclient** (RECOMMENDED - Already in Use)

**Status**: Production-ready, actively maintained
**Package**: `ipfshttpclient` (already in requirements.txt)

**Why Use It**:
- Already integrated with IPFS daemon
- Built-in GossipSub support via IPFS pubsub
- Simple HTTP API, no additional dependencies
- Resilient under 40-60% node churn
- Battle-tested by IPFS ecosystem

**Production Notes**:
- IPFS daemon handles all gossip protocol complexity
- Automatic peer discovery via DHT
- Message deduplication built-in
- No need for custom gossip implementation

**Impact on Implementation**: 
- **Eliminates Phase 3** (GossipSub Communication) - use existing IPFS pubsub
- Reduces from 8 hours to **~5 hours** total development time

### 2. **py-libp2p** (NOT RECOMMENDED)

**Status**: Experimental, not production-ready (as of 2024-2025)
**Package**: `libp2p`

**Why NOT to Use**:
- Explicitly marked as "not for production use" by maintainers
- Missing critical components: NAT traversal, peer discovery (bootstrap, mDNS, rendezvous), Kademlia DHT
- libp2p-quic and libp2p-noise are unstable
- While GossipSub is implemented, the surrounding infrastructure is incomplete

**Verdict**: Avoid until project reaches stable 1.0 release

### 3. **PySyncObj - Raft Consensus** (ALTERNATIVE APPROACH)

**Status**: Production-ready, actively maintained
**Package**: `pysyncobj` (pip install pysyncobj)
**GitHub**: https://github.com/bakwc/PySyncObj

**Why Consider It**:
- Pure Python Raft consensus implementation
- Production-ready, used in real systems
- Built-in leader election
- Replicated state machine
- Supports dynamic cluster membership
- Simpler than custom gossip + voting

**Alternative Architecture**:
Instead of gossipsub + supermajority voting, use Raft:
- Leader node creates proposals
- Raft ensures consensus automatically
- Built-in log replication
- Automatic failover

**Trade-offs**:
- Requires leader election (adds ~2-3 seconds on failover)
- More centralized than gossipsub (leader-based)
- May be overkill for playlist selection
- Requires direct TCP connections between nodes

**Verdict**: Good alternative if IPFS pubsub proves unreliable, but adds complexity

### 4. **etcd with python-etcd3** (NOT RECOMMENDED for our use case)

**Status**: Production-ready, used by Kubernetes
**Package**: `etcd3` (requires separate etcd server)

**Why NOT to Use**:
- Requires deploying separate etcd cluster
- Adds infrastructure complexity
- Designed for strongly consistent key-value store, not P2P gossip
- Overkill for playlist coordination
- Not decentralized (needs etcd servers)

**Verdict**: Wrong tool for this job

### 5. **Apache ZooKeeper with Kazoo** (NOT RECOMMENDED)

**Status**: Production-ready, mature
**Package**: `kazoo` (requires ZooKeeper cluster)

**Why NOT to Use**:
- Requires separate ZooKeeper infrastructure
- Java dependency
- Centralized coordination service (not P2P)
- Significantly more complex than needed
- etcd is better alternative if centralized coordination needed

**Verdict**: Wrong architecture for decentralized radio

### 6. **Vector Clocks / CRDTs** (NOT NEEDED)

**Status**: Various implementations available
**Packages**: Multiple CRDT libraries exist

**Why NOT to Use**:
- We need consensus (agreement), not eventual consistency
- Playlist selection requires deterministic outcome
- CRDTs solve different problem (conflict-free merging)
- Over-engineering for our use case

**Verdict**: Not applicable to consensus problem

---

## Revised Implementation Recommendation

### Approach A: IPFS PubSub (RECOMMENDED)

**Use existing IPFS infrastructure**:

1. **GossipSub**: Use `ipfs.pubsub.pub()` and `ipfs.pubsub.sub()` directly
2. **Peer Discovery**: Automatic via IPFS DHT
3. **Message Propagation**: Handled by IPFS daemon
4. **No Additional Dependencies**: Already have ipfshttpclient

**Implementation Changes**:

```python
# Phase 3 becomes trivial:
class GossipService:
    def __init__(self, ipfs_api, topic):
        self.ipfs = ipfshttpclient.connect(ipfs_api)
        self.topic = topic
    
    def publish_proposal(self, proposal):
        message = json.dumps(proposal).encode('utf-8')
        self.ipfs.pubsub.pub(self.topic, message)
    
    def subscribe_to_proposals(self, callback):
        for message in self.ipfs.pubsub.sub(self.topic):
            data = json.loads(message['data'].decode('utf-8'))
            callback(data)
```

**Benefits**:
- Uses battle-tested IPFS gossipsub
- Zero additional dependencies
- Automatic peer discovery
- Resilient to network partitions
- Already integrated with our stack

**Revised Timeline**: 5 hours (down from 8 hours)

### Approach B: PySyncObj Raft (FALLBACK)

**Only if IPFS pubsub proves unreliable**:

1. Deploy PySyncObj on each node
2. Use Raft for consensus
3. Leader proposes playlist
4. Automatic replication

**Trade-off**: More centralized (leader-based), but stronger consistency guarantees

**Timeline**: 6-7 hours (similar to original, different architecture)

---

## Updated Implementation Plan

### Phase 1: Time Sync & Block Logic (1 hour) - UNCHANGED

### Phase 2: Proposal Creation (1.5 hours) - UNCHANGED

### Phase 3: IPFS PubSub Communication (0.5 hours) - SIMPLIFIED

**Change**: Use IPFS pubsub directly, no custom implementation

**New Step 3.1**: Test IPFS pubsub manually
```bash
# Terminal 1: Subscribe
docker exec sleetbubble-ipfs-node1 ipfs pubsub sub /sleetbubble/consensus/v1

# Terminal 2: Publish
docker exec sleetbubble-ipfs-node1 ipfs pubsub pub /sleetbubble/consensus/v1 "test message"
```

**New Step 3.2**: Create minimal gossip wrapper
- Just wraps ipfshttpclient pubsub methods
- JSON encoding/decoding
- Error handling

**Time Saved**: 30 minutes (from 1 hour to 0.5 hours)

### Phase 4: Coordination & Voting (1.5 hours) - UNCHANGED

### Phase 5: Pin Management (1 hour) - UNCHANGED

### Phase 6: Service Integration (1.5 hours) - REDUCED

**Change**: No custom pubsub service needed

**Time Saved**: 30 minutes

### Phase 7: Multi-Node Testing (1 hour) - UNCHANGED

**Revised Total Time**: ~5-6 hours (down from 8 hours)

---

## Key Dependencies & Versions

### Production-Ready (Use These):

```txt
ipfshttpclient>=0.8.0a2    # Already in requirements.txt
```

### Optional (If IPFS pubsub insufficient):

```txt
# Only add if needed
pysyncobj>=0.3.12          # Raft consensus (fallback)
```

### NOT Recommended:

```txt
# DO NOT USE (not production-ready)
libp2p                     # Experimental
py-libp2p                  # Not ready for production

# DO NOT USE (wrong architecture)
etcd3                      # Requires separate infrastructure
kazoo                      # Requires ZooKeeper cluster
python-consul              # Requires Consul cluster
```

---

## Production Considerations

### IPFS PubSub Reliability:

**Strengths**:
- Battle-tested in IPFS network
- Handles 40-60% node churn
- Automatic mesh healing
- Message deduplication

**Known Issues**:
- Subscribers may miss first 1-2 messages after joining (warmup period)
- Solution: Include block number in proposals, ignore old blocks
- No message ordering guarantees
- Solution: Our coordinator handles this with block numbers + timestamps

**Best Practices**:
1. Connect to IPFS bootstrap nodes for better connectivity
2. Configure IPFS with public IP for better peer discovery
3. Monitor `ipfs swarm peers` to ensure connectivity
4. Use message IDs to prevent duplicates
5. Implement proposal timeout (60 seconds) for missing messages

### Pin Management Strategy:

**Recommendation**: Only pin consensus winners
- Reduces storage requirements
- Keeps network lean
- Configurable retention (3-10 blocks)
- Automatic cleanup of old blocks

### Consensus Timeouts:

**Recommendation**:
- Block duration: 1800 seconds (30 minutes)
- Proposal timeout: 60 seconds
- Vote collection window: 45 seconds
- Allows time for network propagation

---

## References & Sources

### IPFS & libp2p:
1. libp2p GossipSub Specification: https://github.com/libp2p/specs/tree/master/pubsub/gossipsub
2. IPFS PubSub Documentation: https://docs.ipfs.tech/concepts/pubsub/
3. py-libp2p GitHub: https://github.com/libp2p/py-libp2p (Status: Experimental, not production-ready as of 2024-2025)
4. ipfshttpclient Documentation: https://py-ipfs-http-client.readthedocs.io/
5. IPFS Gateway Best Practices: https://docs.ipfs.tech/how-to/gateway-best-practices/
6. GossipSub Research Paper: "GossipSub: A Secure PubSub Protocol for Unstructured, Decentralised P2P Overlays" - Protocol Labs (2019)
7. libp2p PubSub Resilience Study: https://www.sambent.com/ipfs-libp2p-pubsub-gossip-protocol-resilience-under-node-churn/

### Consensus Algorithms:
8. Raft Consensus Algorithm: https://raft.github.io/raft.pdf
9. PySyncObj GitHub: https://github.com/bakwc/PySyncObj (Production-ready Python Raft implementation)
10. rraft-py PyPI: https://pypi.org/project/rraft-py/ (Python bindings for tikv/raft-rs)
11. Raft Consensus Explained: https://www.mindbowser.com/raft-consensus-algorithm-explained/

### Distributed Coordination:
12. etcd Documentation: https://etcd.io/
13. etcd vs ZooKeeper comparison: https://etcd.io/docs/v3.4/learning/why/
14. Apache ZooKeeper: https://zookeeper.apache.org/
15. Kazoo (Python ZooKeeper client): https://kazoo.readthedocs.io/
16. Vector Clocks in Distributed Systems: https://www.geeksforgeeks.org/computer-networks/vector-clocks-in-distributed-systems/

### Alternative P2P Databases:
17. OrbitDB: https://orbitdb.org/ (JavaScript-only, no mature Python implementation)
18. OrbitDB Architecture: Uses IPFS + libp2p pubsub for distributed databases

### Python Async & Distributed Systems:
19. Python asyncio Documentation: https://docs.python.org/3/library/asyncio.html
20. Asynchronous Programming with asyncio (2024): https://www.paulnorvig.com/guides/asynchronous-programming-with-asyncio-in-python.html
21. Temporal Python: https://temporal.io/ (Durable distributed asyncio - overkill for our use case)

### CRDT Resources:
22. CRDTs Explained: https://dev.to/foxgem/crdts-achieving-eventual-consistency-in-distributed-systems-296g
23. Conflict-free Replicated Data Types: https://en.wikipedia.org/wiki/Conflict-free_replicated_data_type

### Community Discussions:
24. GossipSub Message Ordering: https://discuss.libp2p.io/t/gossipsub-message-ordering-and-consensus/2240
25. py-libp2p Production Readiness: https://github.com/libp2p/py-libp2p/issues/947 (Interoperability issues)
26. IPFS PubSub Reliability: https://stackoverflow.com/questions/57224321/how-to-achieve-ipfs-pubsub-room-reliability

### Additional Research:
27. Python Vector Clock Implementation: https://github.com/apurvsinghgautam/VectorClock
28. DistributedClocks Project: https://distributedclocks.github.io/
29. IPFS Streaming Video Example: https://github.com/desiredState/IPFSStreamingVideo (Similar use case)

---

## Decision Summary

**RECOMMENDED APPROACH**: Use IPFS PubSub (already integrated)

**Rationale**:
1. Already have ipfshttpclient in stack
2. IPFS daemon handles all gossipsub complexity
3. Production-ready and battle-tested
4. Reduces development time by 30-40%
5. No additional infrastructure needed
6. Fits decentralized P2P architecture perfectly

**Fallback**: PySyncObj (Raft) if IPFS pubsub proves unreliable in testing

**Avoid**: py-libp2p (not production-ready), etcd/ZooKeeper (wrong architecture), CRDTs (wrong problem)
