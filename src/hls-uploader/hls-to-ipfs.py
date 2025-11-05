#!/usr/bin/env python3
"""
HLS to IPFS Uploader Service
Monitors /hls directory for new .ts segments and uploads them to IPFS immediately.
Tracks CID mappings in a state file for playlist generation.
"""

import os
import sys
import json
import time
import requests
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from datetime import datetime
from collections import OrderedDict

# Configuration
IPFS_API = os.getenv('IPFS_API', 'http://ipfs:5001')
HLS_DIR = os.getenv('HLS_DIR', '/hls')
STATE_DIR = os.getenv('STATE_DIR', '/state')
STATE_FILE = os.path.join(STATE_DIR, 'ipfs_segments.json')
MAX_SEGMENTS = int(os.getenv('MAX_SEGMENTS', '50'))  # Keep last 50 segments per quality
NODE_ID = os.getenv('NODE_ID', 'node1')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format=f'[{NODE_ID}] %(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SegmentState:
    """Manages the state of uploaded segments and their CIDs"""
    
    def __init__(self):
        self.segments = self.load_state()
    
    def load_state(self):
        """Load segment state from disk"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    # Convert to OrderedDict to maintain insertion order
                    return {k: OrderedDict(v) for k, v in data.items()}
            except Exception as e:
                logger.error(f"Failed to load state: {e}")
        return {}
    
    def save_state(self):
        """Save segment state to disk"""
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(STATE_FILE, 'w') as f:
                json.dump(self.segments, f, indent=2)
            logger.debug(f"State saved to {STATE_FILE}")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def add_segment(self, quality, filename, cid, size):
        """Add a new segment to the state"""
        if quality not in self.segments:
            self.segments[quality] = OrderedDict()
        
        self.segments[quality][filename] = {
            'cid': cid,
            'timestamp': int(time.time()),
            'size': size,
            'node_id': NODE_ID
        }
        
        # Keep only the last MAX_SEGMENTS per quality
        if len(self.segments[quality]) > MAX_SEGMENTS:
            # Remove oldest segments
            items_to_remove = list(self.segments[quality].keys())[:-MAX_SEGMENTS]
            for item in items_to_remove:
                removed = self.segments[quality].pop(item)
                logger.info(f"Removed old segment from state: {item}")
                # Optionally unpin old segments (handled by cleanup service)
        
        self.save_state()
    
    def get_segments(self, quality):
        """Get all segments for a quality level"""
        return self.segments.get(quality, OrderedDict())
    
    def get_all_qualities(self):
        """Get list of all quality levels"""
        return list(self.segments.keys())


class HLSSegmentHandler(FileSystemEventHandler):
    """Handles file system events for HLS segments"""
    
    def __init__(self, state):
        self.state = state
        self.processing = set()
    
    def on_closed(self, event):
        """Called when a file is closed after writing"""
        if event.is_directory:
            return
        
        filepath = event.src_path
        filename = os.path.basename(filepath)
        
        # Only process .ts segment files (not .m3u8 playlists)
        if not filename.endswith('.ts'):
            return
        
        # Avoid duplicate processing
        if filepath in self.processing:
            return
        
        self.processing.add(filepath)
        
        try:
            # Small delay to ensure file is complete
            time.sleep(0.1)
            
            # Verify file exists and has content
            if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                logger.warning(f"Skipping invalid file: {filename}")
                self.processing.discard(filepath)
                return
            
            # Extract quality from filename (e.g., "lofi_6_1234567890_1.ts")
            quality = self.extract_quality(filename)
            if not quality:
                logger.warning(f"Could not extract quality from: {filename}")
                self.processing.discard(filepath)
                return
            
            logger.info(f"New segment detected: {filename} ({quality})")
            
            # Upload to IPFS
            cid = self.upload_to_ipfs(filepath)
            
            if cid:
                size = os.path.getsize(filepath)
                self.state.add_segment(quality, filename, cid, size)
                logger.info(f"✓ Uploaded {filename} → {cid} ({size} bytes)")
                
                # Trigger playlist regeneration
                self.trigger_playlist_update()
            else:
                logger.error(f"Failed to upload {filename}")
        
        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")
        finally:
            self.processing.discard(filepath)
    
    def on_modified(self, event):
        """Called when a file is modified"""
        # For .m3u8 files, we might want to update playlists
        if event.is_directory:
            return
        
        filepath = event.src_path
        filename = os.path.basename(filepath)
        
        if filename.endswith('.m3u8'):
            logger.debug(f"Playlist updated: {filename}")
            # Playlist updates are handled by generate-ipfs-playlist.py
    
    def extract_quality(self, filename):
        """Extract quality level from segment filename"""
        # Format: {quality}_{duration}_{timestamp}_{position}.ts
        parts = filename.split('_')
        if len(parts) >= 1:
            quality = parts[0]
            if quality == 'stream':
                return quality
        return None
    
    def upload_to_ipfs(self, filepath):
        """Upload a file to IPFS and return its CID"""
        try:
            with open(filepath, 'rb') as f:
                files = {'file': (os.path.basename(filepath), f)}
                response = requests.post(
                    f'{IPFS_API}/api/v0/add',
                    params={'pin': 'true', 'quiet': 'true'},
                    files=files,
                    timeout=30
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result['Hash']
                else:
                    logger.error(f"IPFS API error: {response.status_code} - {response.text}")
                    return None
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to IPFS API: {e}")
            return None
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return None
    
    def trigger_playlist_update(self):
        """Trigger the playlist generation script"""
        try:
            # The playlist generator runs as a separate service
            # We just need to ensure state is saved, which is already done
            pass
        except Exception as e:
            logger.error(f"Failed to trigger playlist update: {e}")


def process_existing_segments(state):
    """Process any existing segments on startup"""
    logger.info("Scanning for existing segments...")
    
    if not os.path.exists(HLS_DIR):
        logger.warning(f"HLS directory does not exist: {HLS_DIR}")
        return
    
    segment_count = 0
    for filename in os.listdir(HLS_DIR):
        if filename.endswith('.ts'):
            filepath = os.path.join(HLS_DIR, filename)
            
            # Check if already in state
            quality = HLSSegmentHandler(state).extract_quality(filename)
            if quality and filename not in state.get_segments(quality):
                logger.info(f"Processing existing segment: {filename}")
                
                try:
                    cid = HLSSegmentHandler(state).upload_to_ipfs(filepath)
                    if cid:
                        size = os.path.getsize(filepath)
                        state.add_segment(quality, filename, cid, size)
                        segment_count += 1
                        logger.info(f"✓ Uploaded existing {filename} → {cid}")
                except Exception as e:
                    logger.error(f"Error processing existing segment {filename}: {e}")
    
    logger.info(f"Processed {segment_count} existing segments")


def main():
    """Main entry point"""
    logger.info("Starting HLS to IPFS Uploader Service")
    logger.info(f"IPFS API: {IPFS_API}")
    logger.info(f"HLS Directory: {HLS_DIR}")
    logger.info(f"State Directory: {STATE_DIR}")
    logger.info(f"Max Segments per Quality: {MAX_SEGMENTS}")
    
    # Test IPFS connection
    try:
        response = requests.post(f'{IPFS_API}/api/v0/id', timeout=5)
        if response.status_code == 200:
            ipfs_id = response.json()
            logger.info(f"✓ Connected to IPFS node: {ipfs_id['ID'][:16]}...")
        else:
            logger.error("Failed to connect to IPFS API")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Cannot connect to IPFS: {e}")
        sys.exit(1)
    
    # Initialize state
    state = SegmentState()
    logger.info(f"Loaded state with {len(state.segments)} quality levels")
    
    # Process existing segments
    process_existing_segments(state)
    
    # Create HLS directory if it doesn't exist
    os.makedirs(HLS_DIR, exist_ok=True)
    
    # Set up file system watcher
    event_handler = HLSSegmentHandler(state)
    observer = Observer()
    observer.schedule(event_handler, HLS_DIR, recursive=False)
    observer.start()
    
    logger.info(f"👀 Watching {HLS_DIR} for new segments...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        observer.stop()
    
    observer.join()
    logger.info("Service stopped")


if __name__ == '__main__':
    main()
