    
# Streaming refactor

TASKS:
1. read the #codebase very well
2. refactor the streaming process based on the design layout by taking each phase at a time and reporting back.

REQUIREMENTS:
1. do not write comments in code
2. research ALL code, do not ever try and use code from your memory, every decision must be researched
3. do not make extra documentation files, the only documentation you will do will be to track your progress in this file

> Note: **it is of utmost importance** to verify all code patterns, syntax and API usage using the #deepwiki tool or by searching the internet.

---

## The refactoring

in this current architecture, we are encoding music files into HLS segments in real-time from a predetermined playlist file, using liquidsoap. the hls segments are then uploaded to IPFS to receive CID, then the CIDs are gathered together in a playlist that points to ipfs CIDs and that playlist is uploaded to IPFS with IPNS to retain a permanent mutable ID so the content of the playlist can continuously change. the client's music player then takes that playlist file and plays each 6 second segment in a row, then it loops back & the playlist has changed to the next collection of 6 second segments. this create an audio live stream on ipfs.

i want to modify this architecture slightly to make a more robust design. instead of live encoding the music into 6 second hls segments (that gives some stream overhead and syncing issues with the playlist composer), let's shift the entire duty into our own *"in-house HLS segment ipfs streamer"*. we will get rid of liquidsoap entirely, prechunk all of our music into 6 seconds long segments (configurable) and then the streaming service will just deliver continuously whatever segments it has at its disposal (i think right now we make 50 segment of 6 seconds each for each window of stream, this should also be configurable) which means it deals with retrieving the prechunked CIDs and composing the live IPNS mutable playlist with the current window of streaming. essentially the output for the client stays the same, we are just making our sliding window stream much much more efficient and less error prone, because there is no more syncing waiting for liquid soap to generate the chunks so we can clean up and make new ones, no, we just have all the chunks we need already at our disposal, all the streamer service has to do is slide the window to keep the music playing, this means the chunks themselves can change at will which will be important later, because other processes will sit between the audio processing and the audio serving itself so we must separate these 2 processes (a consensus engine aimed at actually deciding what content ends up in the final stream). this also means that the service must be atomical and function independently of other services (except for ipfs obviously because it needs ipfs to stream) its only input being a `processed` folder containing the playlist manifest and all the chunks.

on top of this important architectural refactor i want to add jingles to the radio stream rotation. with the following logic. the system can have any number of jingles but here are 2 examples:
- *with only 2 jingles in the jingle folder:* 
    `jingle1 --> N number of tracks --> jingle2 --> N number of tracks --> jingle1 --> N number of tracks --> jingle2 --> etc`
- *with only 3 jingles in the jingle folder:* 
    `jingle1 --> N number of tracks --> jingle2 --> N number of tracks --> jingle3 --> N number of tracks --> jingle1 --> etc`
essentially we start with jingle, after a configurable amount of tracks we add jingle and so on alternating between all jingles looping when running out. 

---

in order to achieve all these things we must do the following:

1. we need to modify the setup service:
    1. the setup service must use `setup.config` for all the parameters of the setup process
    2. the setup service must first identify music files from the #file:playlist.config.json  (`source` key tells the setup service where to find the music files)
    3. the setup service must then identify the location of jingles (`src/jingles/` folder)
    4. the setup service must then check to see if `data/processed` already has what we need: the correct music prechunked with the correct playlist and correct manifest. if any of these are present and correct it skips that step, if they are present and incorrect (not matching current config) then it redoes those steps
    5. the setup service must then pre-chunk all the music and jingles (if they don't exist or don't match)
    6. the setup service must then create a playlist file, `playlist.m3u`, and the `music_manifest.json` (rename to `manifest.json`) (if the playlist or manifest files dont exist or are incorrect)
    7. the setup service must use the `setup.config` for all paramters of its functionality

2. remove the liquidsoap service and the adjacent services that dealt with playlist building, uploading to ipfs and all that stuff.

3. we need to create the streaming service that will unify all the things of the removed services in the smarter, more robust way i described:
    1. the streaming service runs continuously (after setup is done) and serves our stream.
    2. the streaming service must create a sliding window, that is configurable in its shape, over the content, by smartly analyzing the `playlist.m3u` and using that information to coordinate its movement
    3. the streaming service must create the IPFS IPNS playlist with the prechunked CIDs from the `manifest.json` file and update it in sync with its sliding window computation (this is in effect the sliding window acting)
    4. the streaming service has to be fully configurable for all parameters of its functionality with a `streaming.config` file

4. we need a very lightweight health monitoring service that makes sure the stream is live on the local/public gateways and that it produces audible sounds by measuring dbs and looking at content that is streamed


**these changes will drastically improve our architecture**, making it smaller, robust and more maintanable.

---

## Research & Technical Analysis

This section consolidates research findings essential for implementing the streaming refactor successfully. All technical decisions are grounded in official documentation and established best practices.

### 1. Current Architecture Analysis

**Existing Flow:**
1. Liquidsoap encodes audio → real-time HLS segments (.ts files) in `/data/hls/`
2. `hls-to-ipfs.py` monitors `/data/hls/` using watchdog, uploads segments to IPFS immediately
3. `generate-ipns-playlist.py` creates M3U8 playlists referencing IPFS CIDs
4. IPNS publishes mutable playlists for continuous updates
5. Client fetches from `/ipns/NAME` and plays segments sequentially

**Issues Identified:**
- Real-time encoding creates sync overhead between liquidsoap → uploader → playlist generator
- Race conditions with file system monitoring (segments may be processed before fully written)
- Fixed 6-second segments hardcoded across multiple services
- No jingle support in current rotation logic
- Magic numbers scattered throughout (timeouts, segment counts, durations)

### 2. FFmpeg Pre-chunking Research

**Optimal Command Structure** (based on FFmpeg/FFmpeg documentation):
```bash
ffmpeg -i input.mp3 \
  -c:a aac -b:a 128k \
  -f hls \
  -hls_time 6 \
  -hls_list_size 0 \
  -hls_segment_filename "segment_%03d.ts" \
  output.m3u8
```

**Key Parameters:**
- `-hls_time <duration>`: Target segment length (configurable: 3-10s recommended)
- `-hls_list_size 0`: Keep all segments in playlist (not limited for pre-chunking)
- `-c:a aac -b:a 128k`: AAC codec with consistent bitrate for quality
- `-f hls`: Uses dedicated HLS muxer (preferred over generic `segment` muxer)

**Quality Considerations:**
- Use constant bitrate (CBR) for consistent quality across chunks
- AAC codec provides good compression/quality balance for streaming
- Segment duration 6s balances latency vs overhead (current is appropriate)
- Keyframe alignment handled automatically by HLS muxer

### 3. IPFS API Integration Patterns

**Upload with Pinning** (current pattern working correctly):
```python
files = {'file': open(file_path, 'rb')}
response = requests.post(f'{IPFS_API}/api/v0/add?pin=true', files=files)
cid = response.json()['Hash']
```

**Best Practices:**
- Always use `pin=true` for content that must persist
- Handle network timeouts gracefully (current implementation lacks this)
- Batch operations where possible (upload multiple segments in sequence)
- Verify CID consistency (same content = same CID)

### 4. HLS Streaming Architecture

**M3U8 Playlist Format** for live streams:
```m3u8
#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXT-X-MEDIA-SEQUENCE:1000
#EXTINF:6.0,
/ipfs/QmHash1
#EXTINF:6.0,
/ipfs/QmHash2
```

**Sliding Window Logic:**
- `#EXT-X-MEDIA-SEQUENCE`: Monotonically increasing sequence number
- Keep N segments in playlist (configurable window size)
- Update playlist every few seconds with new segment batch
- Client maintains buffer of 3-5 segments ahead of current playback

**Key Requirements:**
- Consistent `#EXT-X-TARGETDURATION` across all playlists
- Proper sequence numbering prevents playback gaps
- IPFS CID references replace traditional HTTP URLs
- Must maintain segment continuity during window updates

### 5. IPNS Publishing Patterns

**Current Working Implementation:**
```python
# Key creation (done once)
response = requests.post(f'{IPFS_API}/api/v0/key/gen', 
                        params={'arg': key_name, 'type': 'rsa'})

# Content publishing (continuous updates)
response = requests.post(f'{IPFS_API}/api/v0/name/publish',
                        params={'arg': content_cid, 'key': key_name, 
                               'lifetime': '24h', 'ttl': '5s'})
```

**Performance Considerations:**
- IPNS updates can take 5-30 seconds to propagate through DHT
- Use shorter TTL (5s) for faster local resolution
- Lifetime (24h) determines how long record persists without updates
- Public key caching improves subsequent publish performance

### 6. File System Monitoring Optimization

**Watchdog Best Practices:**
```python
# Avoid duplicate processing with delay
def on_closed(self, event):
    time.sleep(0.1)  # Ensure file write completion
    if filepath in self.processing:
        return  # Avoid race conditions
    self.processing.add(filepath)
```

**Performance Improvements:**
- Use `on_closed` event (ensures file is complete) rather than `on_created`
- Implement debouncing for rapid file changes
- Filter by file extensions at handler level
- Use non-recursive monitoring when deep directory watching unnecessary

### 7. Audio Quality Monitoring Techniques

**FFmpeg-based Health Checks:**
```bash
# Silence detection
ffmpeg -i segment.ts -af "silencedetect=noise=-50dB:duration=1" -f null -

# Audio level measurement  
ffmpeg -i segment.ts -af "volumedetect" -f null -

# Integrity verification
ffmpeg -i segment.ts -f hash -hash sha256 -
```

**Implementation Strategy:**
- Sample random segments periodically (not every segment)
- Monitor audio levels to detect silence/corruption
- Use CRC/hash verification for data integrity
- Alert if consecutive silent segments detected

### 8. Playlist Composition with Jingles

**Rotation Algorithm** (based on `jingle_cycle` parameter):
```python
# Example: jingle_cycle=3 means jingle every 3 tracks
track_counter = 0
jingle_index = 0

for track in music_tracks:
    if track_counter > 0 and track_counter % jingle_cycle == 0:
        yield jingles[jingle_index % len(jingles)]
        jingle_index += 1
    yield track
    track_counter += 1
```

**Considerations:**
- Jingles must be pre-chunked same as music tracks
- Maintain separate manifests for jingles vs music
- Handle different audio characteristics (volume normalization may be needed)
- Ensure smooth transitions between jingles and tracks

### 9. Configuration Management

**Hierarchical Config Structure:**
```json
{
  "audio": {
    "segment_duration": 6,
    "bitrate": "128k",
    "codec": "aac"
  },
  "streaming": {
    "window_size": 50,
    "update_interval": 2,
    "max_segments": 20
  },
  "jingles": {
    "cycle": 3,
    "enabled": true
  }
}
```

**Cache Validation Pattern:**
- Compare config hash against previous run
- Rebuild only affected components when config changes
- Store config hash in manifest for validation
- Skip processing when inputs unchanged

### 10. Docker Service Architecture

**Dependency Chain** (critical for startup order):
```yaml
setup → (completes) → streamer → health-monitor
ipfs → (all dependent services)
config-page → (depends on all stream services)
```

**Key Requirements:**
- Setup service runs to completion (`restart: "no"`)
- Streaming service runs continuously (`restart: unless-stopped`)  
- Health monitoring requires streaming service to be operational
- Proper volume mounting for shared state between services

### Sources

**Official Documentation:**
- FFmpeg/FFmpeg Repository - HLS muxer implementation and audio processing filters
- video-dev/hls.js Repository - HLS streaming architecture and sliding window mechanisms
- IPFS Documentation (docs.ipfs.tech) - IPFS HTTP API, pinning, and CID management
- IPNS Specification (specs.ipfs.tech) - InterPlanetary Name System record format and publishing

**Technical References:**
- Python Watchdog Documentation - File system monitoring best practices and performance optimization
- Fleek.xyz IPNS Guide - Mutable naming and record management patterns
- Medium: "IPFS in Python" by Chris Garrett - Python IPFS integration examples
- CodeRivers: "Python Watchdog" - File system event handling and monitoring techniques

**Codebase Analysis:**
- `/workspaces/sleet_test/src/liquidsoap/` - Current audio encoding and HLS generation
- `/workspaces/sleet_test/src/hls-uploader/` - IPFS upload patterns and state management
- `/workspaces/sleet_test/src/playlist-generator/` - IPNS publishing and M3U8 generation
- `/workspaces/sleet_test/docker-compose.yml` - Service dependency architecture
- `/workspaces/sleet_test/docs/codebase-analysis.md` - Existing system strengths and weaknesses

---

## Implementation Plan

### Phase 1: Enhanced Setup Service ✅ COMPLETED

**What**: Refactor setup service to pre-chunk music/jingles and generate comprehensive manifest

**Technical Changes**:

- ✅ Create `setup.config.json` parser with segment_duration, jingle_cycle, bitrate, codec params
- ✅ Build cache validation logic (compare manifest hash against current config)
- ✅ Integrate FFmpeg chunking with `-vn` flag to strip album art for proper audio segmentation
- ✅ Add jingles processing from `src/jingles/` folder
- ✅ Generate unified `manifest.json` with track metadata + segment CIDs
- ✅ Create `playlist.m3u` with interleaved jingles based on jingle_cycle config
- ✅ Created `src/setup/setup_processor.py` - unified setup logic
- ✅ Updated `setup.sh` to call new processor

**Testing Results**:

- ✅ Run setup with empty `data/processed` → chunks everything properly
- ✅ Run setup again → skips processing (cache hit validated)
- ✅ Change config param (segment_duration 6→8) → detects change and re-chunks
- ✅ Manifest contains all 6 tracks + 3 jingles with correct CID mappings
- ✅ Playlist.m3u alternates jingles every 2 tracks as configured
- ✅ All audio files properly segmented (24, 9, 7, 30, 78, 33 segments respectively)

**Key Fix**: Added `-vn` flag to FFmpeg command to strip album art (video stream), which was preventing proper HLS audio segmentation for files with embedded cover images.

### Phase 2: New Streaming Service ✅ COMPLETED

**What**: Replace liquidsoap + uploader + playlist-generator with unified streaming service

**Technical Changes**:

- ✅ Create `src/streamer/` with main loop and sliding window logic
- ✅ Load manifest.json and playlist.m3u on startup
- ✅ Implement window cursor that tracks current position in playlist
- ✅ Build HLS m3u8 generator that references pre-chunked segment CIDs
- ✅ Integrate IPNS publishing (reuse existing IPNS manager code)
- ✅ Add `streaming.config` with window_size, update_interval, max_segments params
- ✅ Update window every N seconds, regenerate and republish playlist

**Implementation Notes**:
- Created `streaming.config.json` with configurable parameters
- Implemented sliding window that advances by 1 segment every N updates
- Window shows 30 segments, updates every 3 seconds, advances every 2 updates
- Generates proper HLS live playlist (no EXT-X-ENDLIST, incrementing MEDIA-SEQUENCE)
- IPNS publishing works correctly with local/public gateway

**Phase 2 Issues & Resolutions**:

1. **Playlist Format** ✅ FIXED
   - Issue: Playlist generation was already correct (no EXT-X-ENDLIST for live streams)
   - Confirmed: Using proper HLS live stream format per RFC 8216

2. **Sequence Persistence** ✅ FIXED
   - Issue: Sequence numbers reset on streamer restart, confusing HLS players
   - Solution: Implemented `sequence_state.json` persistence
   - Result: Sequence numbers now monotonically increase across restarts
   - Implementation: Added `load_sequence_state()` and `save_sequence_state()` methods
   - File: `/data/state/sequence_state.json` stores position, sequence, timestamp

3. **Client-Side HLS Configuration** ✅ FIXED
   - Issue: HLS.js not optimized for live IPNS streaming
   - Changes:
     - Reduced buffer sizes (30s/60s vs 60s/120s) for lower latency
     - Added `startPosition: -1` to always start at live edge
     - Added Cache-Control headers via xhrSetup for IPNS requests
     - Reduced `backBufferLength` to 15s for better memory management

4. **IPNS Caching** ✅ FIXED
   - Issue: Browser/gateway caching old IPNS resolutions on page refresh
   - Solution: Added timestamp query parameter to gateway URLs
   - Implementation: Each playlist request gets `?t={timestamp}` appended
   - Result: Forces fresh IPNS resolution on every request
   - IPFS gateways ignore unknown query params, so CID stays same

5. **Gateway IPNS Cache TTL** ✅ FIXED
   - Issue: IPFS Kubo gateway was caching IPNS resolutions indefinitely
   - Solution: Added `MaxCacheTTL: "5s"` to Ipns config in `/data/ipfs/config`
   - Result: Gateway now re-resolves IPNS records every 5 seconds max
   - Note: Requires IPFS daemon restart to take effect

6. **Live Edge Synchronization** ✅ FIXED
   - Issue: Each client starts from beginning instead of joining live edge
   - Root Cause: HLS.js cannot calculate live edge without timing information
   - Solution: Added `#EXT-X-PROGRAM-DATE-TIME` tags to each segment in playlist
   - Implementation: Streamer calculates wall-clock time for each segment based on window position
   - HLS.js Config: Reduced buffer sizes (18s/36s), `liveSyncDurationCount: 2` for tighter sync
   - Active Monitoring: Added `LEVEL_UPDATED` event handler to detect high latency (>18s) and seek to live edge
   - Result: All clients now join at the current live position, not the beginning

7. **Aggressive Cache Busting** ✅ FIXED
   - Issue: Browser and IPFS caching preventing real-time playlist updates
   - Solution: Added timestamp query params to all manifest/segment requests in xhrSetup
   - Implementation: `xhr.open('GET', url + '?t=' + Date.now(), true)` for all HLS requests
   - Headers: Set Cache-Control, Pragma, Expires headers on all XHR requests
   - Result: Every playlist/segment fetch bypasses all cache layers

8. **Media Sequence Bug** ✅ FIXED
   - Issue: `#EXT-X-MEDIA-SEQUENCE` always set to 0, causing clients to restart from beginning
   - Root Cause: Calculation `max(0, sequence_number - max_segments + 1)` produced 0 when sequence < max_segments
   - Solution: Changed to use `self.sequence_number` directly for proper live edge tracking
   - Result: Clients now correctly join at current live position, sync maintained across all listeners

**Known Limitations** (Future Improvements):
- 🔄 **Segment Window Serving**: Current implementation serves segments based on circular buffer position. Consider optimizing window composition algorithm for better predictability and edge-case handling (e.g., when playlist length < window size, or during playlist updates)

**Testing Results**:

- ✅ Stream loads and plays correctly
- ✅ Sliding window advances smoothly
- ✅ Sequence numbers persist across restarts
- ✅ IPNS updates propagate with 5s TTL
- ✅ Cache-busting prevents stale playlist fetches
- ✅ Gateway IPNS MaxCacheTTL set to 5s
- ✅ Program-date-time tags added for proper live edge calculation
- ✅ HLS.js configured for low-latency live streaming
- ✅ Active latency monitoring with automatic seek to live edge
- ✅ Media sequence bug fixed - clients join at live edge
- ✅ Multiple clients now synchronized to same live position
- ✅ Page refresh joins current live position, not beginning
- ✅ Legacy services (liquidsoap, uploader, playlist, segment-cleanup) **STOPPED**
- ✅ New streamer is now the sole playlist generator

**Files Modified**:
- `src/streamer/streamer.py` - Fixed media sequence bug, added sequence state persistence, program-date-time tags
- `src/config-page/index.html` - Updated HLS.js config with live edge sync logic and aggressive cache busting
- `data/ipfs/config` - Added `MaxCacheTTL: "5s"` to Ipns section
- `streaming.config.json` - Configuration parameters

**Services Status**:
- ✅ Running: ipfs, setup, streamer, state-sync, config-page
- ⛔ Stopped: liquidsoap, uploader, playlist, segment-cleanup (legacy services ready for removal)

**Phase 2 Complete**: Unified streaming service fully operational with live synchronization across all clients. Ready to proceed with Phase 3 cleanup.

### Phase 3: Remove Legacy Services ✅ COMPLETED

**What**: Clean up liquidsoap, hls-uploader, playlist-generator, segment-cleanup

**Technical Changes**:

- ✅ Remove services from docker-compose.yml: liquidsoap, uploader, playlist, segment-cleanup
- ✅ Delete directories: `src/liquidsoap/`, `src/hls-uploader/`, `src/playlist-generator/`, `src/segment-cleanup/`, `src/playlist/`
- ✅ Remove `/data/hls/` volume mount (no longer needed)
- ✅ Update state-sync to only handle stream metadata (verified - no segment tracking)
- ✅ Clean up unused dependencies from requirements.txt (removed watchdog)

**Implementation Notes**:

- Uncommented and activated state-sync and config-page services in docker-compose.yml
- Removed all legacy service directories from src/ folder
- Removed watchdog dependency (only used by old hls-uploader)
- Removed legacy verification script `src/utils/verify-ipfs-streaming.sh`
- Cleaned up legacy Docker images (liquidsoap, uploader, playlist, segment-cleanup)
- State-sync service confirmed to only handle distributed state synchronization via IPFS pubsub (no HLS/segment logic)

**Testing Results**:

- ✅ `docker compose up` starts only: ipfs, setup, streamer, state-sync, config-page
- ✅ No orphaned containers or volumes
- ✅ Stream confirmed working end-to-end (IPNS publishing, sequence tracking)
- ✅ All services healthy and running properly
- ✅ Legacy Docker images removed, disk space reclaimed

**Services Status**:
- ✅ Running: ipfs, setup (completed), streamer, state-sync, config-page
- ⛔ Removed: liquidsoap, uploader, playlist, segment-cleanup

**Phase 3 Complete**: Architecture successfully cleaned up. System now runs on unified streamer with pre-chunked content. Ready for Phase 4 (health monitoring) if needed.

### Phase 4: Health Monitor Service

**What**: Lightweight service to verify stream health

**Technical Changes**:

- Create `src/health-monitor/` with periodic checks
- Fetch IPNS playlist from local gateway (http://ipfs:8080/ipns/...)
- Download latest segment and verify it's valid HLS/audio
- Use ffmpeg to measure audio levels (detect silence/corruption)
- Publish health metrics to `/state/health.json` 
- Optional: Ping public gateways (ipfs.io, dweb.link) for availability

**Testing**:

- Monitor detects healthy stream → green status
- Stop streamer → monitor reports unhealthy
- Corrupt a segment CID in manifest → monitor detects invalid audio
- Generate silent audio → monitor detects low dB levels
- Check metrics update every 30-60 seconds

### Phase 5: Integration & Documentation

**What**: End-to-end validation and config documentation

**Technical Changes**:

- Update README.md with new architecture diagram
- Document all config files: setup.config, streaming.config
- Create example configs for different use cases
- Update .env.example if needed

**Testing**:

- Fresh deployment test: clone repo → add music → docker compose up
- Verify stream starts within 5 minutes
- Test with different configs: short segments (3s), long windows (100 segments)
- Test jingle_cycle variations (1, 5, 10 tracks between jingles)
- Load test with 10+ concurrent HLS clients
- Verify IPNS updates remain fast (<5s) under load

---

### Progress Tracker

