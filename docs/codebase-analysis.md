# Codebase Analysis: Strengths and Weaknesses

## Good Parts

### 1. Strong Architectural Vision
The project has a clear architectural approach combining IPFS, IPNS, Liquidsoap, and Docker for truly decentralized radio streaming. The IPNS mutable addressing strategy is particularly elegant, providing permanent URLs while content continuously updates.

### 2. Service-Oriented Design
Docker Compose orchestrates 6 specialized services with clear separation of concerns:
- `ipfs`: Content storage and P2P networking
- `liquidsoap`: Audio encoding and HLS generation
- `state-sync`: Distributed consensus via PubSub
- `hls-uploader`: Real-time segment uploading
- `playlist-generator`: IPNS playlist management
- `segment-cleanup`: Storage lifecycle management

Each service has a single, well-defined responsibility.

### 3. Real-Time Processing Pipeline
The watchdog-based file monitoring in `hls-to-ipfs.py` provides immediate segment upload after creation, enabling low-latency streaming. The `on_closed` event handler ensures files are fully written before processing.

### 4. State Management
Using JSON files for persistent state (`ipfs_segments.json`, `ipns_keys.json`, `stream_info.json`) is simple and debuggable. The OrderedDict-based segment tracking maintains insertion order for proper cleanup.

### 5. Graceful Degradation
Scripts like `state-sync.py` implement retry logic and timeout handling. Services use `restart: unless-stopped` to recover from transient failures automatically.

### 6. Multi-Quality Streaming
Three bitrate levels (lofi/midfi/hifi) provide flexibility for different network conditions and listener preferences, all published to separate IPNS names.

## Shortcomings and Flaws

### 1. No Error Handling Strategy
**Severity: High**

Python scripts use inconsistent error handling patterns:
- Some use `logging.error()` (good)
- Some use `print(f"Error: ...")` (poor)
- Many have bare `except Exception as e:` blocks that swallow errors
- No structured logging or error aggregation
- No monitoring or alerting hooks

Example from `hls-to-ipfs.py`:
```python
except Exception as e:
    logger.error(f"Error processing {filename}: {e}")
    # Then what? No recovery, no alerting, just continues
```

### 2. Missing Test Coverage
**Severity: Critical**

Zero test files exist. No unit tests, integration tests, or end-to-end tests for:
- IPFS upload/download logic
- Playlist generation correctness
- State synchronization algorithms
- Segment cleanup edge cases
- IPNS publishing failures
- Docker service health

### 3. Hardcoded Magic Numbers
**Severity: Medium**

Constants scattered throughout without centralized configuration:
- Segment duration (6 seconds) duplicated in liquidsoap config and Python
- Timeouts vary arbitrarily (2s, 5s, 10s, 30s, 120s, 300s)
- `MAX_SEGMENTS=50` is reasonable but not justified
- `UPDATE_INTERVAL=3` seconds lacks explanation
- `SEGMENT_RETENTION_TIME=300` (5 min) seems arbitrary

### 4. Race Conditions and Timing Issues
**Severity: Medium**

The deployment script uses fixed `sleep` delays:
```bash
sleep 20  # "Waiting for IPFS to be ready"
sleep 10  # "Waiting for services to initialize"
```

Services can start in unpredictable order. No proper health checks or readiness probes despite Docker Compose supporting them.

### 5. Incomplete Requirements Management
**Severity: Medium**

`requirements.txt` only lists two packages:
```
requests==2.31.0
watchdog==3.0.0
```

But Python scripts also use:
- `json`, `os`, `sys`, `time` (stdlib - fine)
- `logging`, `pathlib`, `datetime` (stdlib - fine)
- No version pinning for Docker base images
- `Dockerfile.liquidsoap` installs system packages without version locks

### 6. Inconsistent Logging
**Severity: Medium**

Three different logging approaches:
1. `logging.basicConfig()` with structured formatting (hls-to-ipfs.py, cleanup-old-segments.py)
2. Plain `print()` statements (pin-music.py, prepare-music.py)
3. Liquidsoap's custom log functions

No centralized log aggregation or correlation IDs for distributed tracing.

### 7. State File Corruption Risk
**Severity: Medium**

JSON state files are written without atomic operations:
```python
with open(STATE_FILE, 'w') as f:
    json.dump(self.segments, f, indent=2)
```

If the process crashes mid-write, the state file gets corrupted. Should use temp file + atomic rename pattern:
```python
temp_file = STATE_FILE + '.tmp'
with open(temp_file, 'w') as f:
    json.dump(data, f)
os.rename(temp_file, STATE_FILE)
```

### 8. Memory Leak Potential
**Severity: Low-Medium**

In `state-sync.py`, `remote_states` dictionary grows unbounded:
```python
self.remote_states[node_id] = {...}
```

The cleanup thread runs every 60 seconds and only removes states older than 10 minutes. In a network with many transient nodes, this could accumulate significant memory.

### 9. No Input Validation
**Severity: Medium**

Scripts blindly trust environment variables and user input:
- `NODE_ID` could contain shell injection characters
- No validation that `MAX_SEGMENTS` is positive
- Paths from environment variables not sanitized
- File extensions checked with simple string matching, not proper MIME types

### 10. Duplicate Code
**Severity: Low**

IPFS API calls are duplicated across multiple scripts:
- `requests.post(f'{IPFS_API}/api/v0/add', ...)` in 4+ places
- Wait-for-IPFS loops copied in 3 scripts
- JSON state loading/saving duplicated

Should be extracted to a shared `ipfs_client.py` module.

### 11. Unclear Consensus Implementation
**Severity: High**

The `CONSENSUS-MODEL.md` describes a sophisticated deterministic random selection algorithm, but `state-sync.py` only implements basic state broadcasting. The actual consensus logic appears to be missing or not yet implemented.

This is a major gap between design and implementation.

### 12. No Graceful Shutdown
**Severity: Medium**

Python services use infinite `while` loops without signal handling:
```python
while self.running:
    time.sleep(10)
```

The `self.running` flag is only set by KeyboardInterrupt, not SIGTERM from Docker. Services won't flush state or clean up resources on container stop.

### 13. Security Concerns
**Severity: Medium**

- No authentication for IPFS API access (anyone on network can publish)
- State files world-readable in Docker volumes
- No rate limiting on IPNS publishes
- PubSub topics not encrypted or authenticated
- No verification of segment CIDs before playing

### 14. Docker Anti-Patterns
**Severity: Low**

- `Dockerfile.state-sync` reused for 4 different services (confusing)
- No `.dockerignore` file (bloated build contexts)
- Root user in containers (`set("init.allow_root", true)`)
- No multi-stage builds to reduce image size

### 15. Monitoring and Observability Gaps
**Severity: High**

Zero instrumentation:
- No metrics (Prometheus, statsd)
- No distributed tracing
- No performance profiling
- Can't answer: "How many segments uploaded?" "What's the average upload time?" "How much IPFS storage used?"
- Only way to debug is tailing logs manually

## Summary

**Strengths**: Clean architecture, good service separation, real-time processing, Docker orchestration

**Critical Issues**: No tests, incomplete consensus implementation, poor error handling, missing observability

**Quick Wins**: Add health checks, centralize configuration, implement atomic state writes, add structured logging

**Long-term Needs**: Test suite, monitoring stack, security hardening, consensus algorithm completion
