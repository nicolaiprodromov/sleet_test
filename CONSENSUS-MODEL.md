# Decentralized DJ Consensus Model

## Overview

A fully decentralized P2P radio station where each node acts as an independent DJ, proposing tracks from their own unique playlists. Track selection happens through deterministic random consensus via IPFS PubSub, creating an emergent, collaborative radio experience.

## Core Principles

### 1. **No Leader Architecture**
- All nodes are equal peers
- No permanent authority or hierarchy
- Pure decentralization through deterministic randomness

### 2. **Independent Playlists**
- Each node maintains its own unique music library
- Nodes propose tracks from their personal collections
- Network playlist emerges from collective proposals

### 3. **Deterministic Random Selection**
- Winning track chosen by cryptographic hash-based randomness
- All nodes independently calculate the same result
- No coordination required, fully Byzantine-resistant

### 4. **Lazy Loading via IPFS**
- Winner shares pre-chunked HLS segments
- Other nodes fetch segments progressively
- IPFS ensures decentralized content distribution

## Consensus Timeline

### **5-Song Lookahead Window**
The system always maintains consensus on the **next 5 tracks** in the queue:

```
Current Playing: Track N
Queue: [Track N+1, Track N+2, Track N+3, Track N+4, Track N+5]
         └─────────── decided ─────────────┘
```

### **3-Song Consensus Period**
Consensus for Track N+5 happens during playback of Tracks N, N+1, and N+2:

```
Track N Playing     → Propose Track N+5
Track N+1 Playing   → Select winner for Track N+5  
Track N+2 Playing   → Fetch segments for Track N+5
Track N+3 Playing   → Track N+5 ready in queue
Track N+4 Playing   → Track N+5 moves up
Track N+5 Playing   → ✅ Seamless playback
```

## Consensus Phases

### **Phase 1: Proposal (During Track N)**
- **Duration**: First 30 seconds or 25% of track duration
- **Action**: Each node proposes one track from their playlist
- **Message**: 
```json
{
  "type": "PROPOSAL",
  "node_id": "node-abc123",
  "track_name": "Song Title",
  "track_hash": "sha256:...",
  "duration": 240,
  "segments": ["Qm...", "Qm...", ...],
  "playlist_hash": "sha256:...",
  "track_index": 5,
  "timestamp": 1699123456,
  "target_slot": 5
}
```

### **Phase 2: Selection (During Track N+1)**
- **Duration**: First 60 seconds or 40% of track duration
- **Action**: All nodes run deterministic random selection
- **Algorithm**:
```python
# All nodes calculate same result
seed = f"{slot_start_time}-{sorted_track_hashes}"
winner_index = sha256(seed) % num_proposals
```

### **Phase 3: Fetching (During Track N+2)**
- **Duration**: Entire track duration (avg 3-4 minutes)
- **Action**: Nodes fetch winning track segments from IPFS
- **Parallelization**: IPFS fetches from multiple peers simultaneously
- **Buffer**: 3 full songs (9-12 minutes) ensures retrieval even on slow connections

## Deduplication & Fairness

### **Playlist Hashing**
Prevents duplicate proposals from nodes with identical playlists:

```python
playlist_hash = sha256(
    "|".join([f"{track.hash}:{track.index}" for track in sorted(playlist)])
)

# If proposal exists with same (playlist_hash + track_index), skip
```

### **Track Deduplication**
Multiple nodes proposing the same track (different sources):
- Keep only the first proposal (by timestamp)
- Ensures fair representation without redundancy

### **Equal Opportunity**
- Each node proposes once per consensus round
- Random selection gives all proposals equal chance
- No node can game the system without controlling time itself

### **Content Moderation & Network Consensus**

**Flexible Local Moderation with Consensus Tracking:**

Each node can apply **custom moderation filters** (blacklists, content filters, etc.) but must track and broadcast when it diverges from network consensus:

```python
# Example: Node applies local blacklist
def apply_local_moderation(winning_track):
    """Node can reject tracks based on local preferences"""
    if winning_track["track_name"] in my_blacklist:
        return False  # I won't play this
    return True

# After selection, nodes broadcast what they're ACTUALLY playing
def broadcast_playback_state(selected_track, actually_playing_track):
    """
    Nodes must be honest about divergence
    """
    consensus_hash = sha256(selected_track["track_hash"])
    actual_hash = sha256(actually_playing_track["track_hash"])
    
    state = {
        "consensus_hash": consensus_hash,  # What network agreed on
        "actual_hash": actual_hash,        # What I'm actually playing
        "diverged": consensus_hash != actual_hash,
        "node_id": self.node_id
    }
    broadcast(state)
```

**Divergence Detection & Auto-Exclusion:**

1. **Consensus State Tracking**
   - After deterministic selection, all nodes calculate `consensus_track_hash`
   - Each node broadcasts: `{consensus_hash, actual_playing_hash, diverged: bool}`
   - Network monitors which nodes are diverged vs. synchronized

2. **Automatic Exclusion**
```python
def check_node_sync_status(node_id):
    """
    Track how long a node has been diverged
    """
    if node_states[node_id]["diverged"]:
        divergence_duration = time.time() - divergence_start[node_id]
        
        if divergence_duration > 600:  # Diverged for 10+ minutes
            excluded_nodes.add(node_id)
            print(f"🚫 {node_id} excluded: prolonged divergence")
            return False
    else:
        # Node is back in sync
        if node_id in excluded_nodes:
            excluded_nodes.remove(node_id)
            print(f"✅ {node_id} rejoined consensus")
    
    return node_id not in excluded_nodes
```

3. **Consensus Participation**
   - Only synchronized nodes participate in proposal/selection
   - Diverged nodes still receive broadcasts but their proposals are ignored
   - When diverged node plays the same track as consensus → auto-rejoin

**Key Properties:**
- ✅ **Freedom**: Nodes can moderate however they want
- ✅ **Transparency**: Divergence is publicly visible
- ✅ **Self-Regulating**: Network automatically excludes diverged nodes
- ✅ **Recoverable**: Nodes can rejoin by syncing back to consensus
- ✅ **No Censorship**: No central authority decides moderation rules

**Example Flow:**
```
Consensus selects: Track A (hash: abc123)

Node 1: Playing Track A (abc123) → ✅ In consensus
Node 2: Playing Track A (abc123) → ✅ In consensus  
Node 3: Rejected Track A (blacklisted), playing Track B (xyz789) → ⚠️ Diverged
  └─ Node 3 excluded from next round of proposals
  └─ After 3 consecutive divergences: temporarily banned
```

## Initial Bootstrap

### **First Deployment**
The deployer establishes the initial 5-track queue:

```json
{
  "bootstrap": true,
  "initial_queue": [
    {"track": "...", "start_time": 1699123456},
    {"track": "...", "start_time": 1699123696},
    {"track": "...", "start_time": 1699123936},
    {"track": "...", "start_time": 1699124176},
    {"track": "...", "start_time": 1699124416}
  ]
}
```

All nodes sync to this initial state, then normal consensus begins for Track 6 onwards.

## Technical Implementation

### **Pre-Chunking at Deployment**
Each node pre-processes their playlist on startup:
```bash
1. Read music files from local directory
2. Generate HLS segments (6-second chunks)
3. Pin all segments to local IPFS node
4. Broadcast catalog with IPFS CIDs
5. Hash entire playlist for deduplication
```

### **State Synchronization**
Nodes broadcast current state every 5 seconds:
```json
{
  "node_id": "node-abc123",
  "current_track": {"name": "...", "hash": "..."},
  "position": 142.5,
  "queue": ["hash1", "hash2", "hash3", "hash4", "hash5"],
  "timestamp": 1699123456
}
```

### **New Node Joining**
1. Listen for state broadcasts from existing nodes
2. Fetch current queue (5 tracks) from IPFS
3. Sync to current playback position
4. Begin participating in next consensus round

## Advantages

✅ **Fully Decentralized**: No leader, no central authority
✅ **Censorship Resistant**: No single playlist to control
✅ **Scalable**: Nodes can join/leave freely
✅ **Creative**: Emergent playlist from multiple DJs
✅ **Fair**: Deterministic randomness ensures equality
✅ **Robust**: 5-song buffer survives network issues
✅ **Efficient**: Lazy loading minimizes bandwidth
✅ **Byzantine Tolerant**: Honest majority not required for sync

## Edge Cases

### **No Proposals in Round**
- Fallback: Each node continues with their own playlist
- Re-sync in next consensus round

### **IPFS Fetch Failure**
- 3-song window provides ample retry time
- Fallback: Request from different IPFS peers
- Ultimate fallback: Skip to next available track

### **Network Partition**
- Each partition runs independent consensus
- Partitions diverge temporarily
- Automatic re-sync when partition heals

### **Malicious Node**
- Can only propose bad tracks from own playlist
- Random selection limits impact to ~1/N probability
- Cannot disrupt other nodes' consensus calculation

### **Node Using Modified Validation Rules**
- Proposals rejected by honest nodes (rules hash mismatch)
- Accumulates violation count in peer reputation system
- Automatically excluded from consensus after 3+ violations
- Cannot participate until it adopts canonical rules

## Future Enhancements

- **Reputation System**: Weight proposals by node uptime/reliability
- **Genre Tagging**: Thematic consensus (e.g., only electronic music)
- **Voting System**: Listeners can vote to influence selection probability
- **Dynamic Buffer**: Adjust lookahead based on network conditions
- **Cross-Seeding**: Nodes cache popular tracks proactively
- **Community Moderation Governance**: 
  - Nodes vote on new moderation criteria via PubSub proposals
  - Majority approval required to add/modify validation rules
  - Decentralized content policy evolution
  - Example: Vote to allow/disallow explicit content, set genre restrictions, etc.

---

**Summary**: A truly decentralized radio station where the playlist emerges from democratic random selection across independent DJs, synchronized through cryptographic consensus and distributed via IPFS.
