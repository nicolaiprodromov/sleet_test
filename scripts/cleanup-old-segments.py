#!/usr/bin/env python3
"""
IPFS Segment Cleanup Service
Manages IPFS storage by unpinning old segments that are no longer needed.
Keeps only the last N segments per quality level.
"""

import os
import sys
import json
import time
import requests
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
IPFS_API = os.getenv('IPFS_API', 'http://ipfs:5001')
HLS_DIR = os.getenv('HLS_DIR', '/hls')
STATE_DIR = os.getenv('STATE_DIR', '/state')
STATE_FILE = os.path.join(STATE_DIR, 'ipfs_segments.json')
NODE_ID = os.getenv('NODE_ID', 'node1')
MAX_SEGMENTS = int(os.getenv('MAX_SEGMENTS', '50'))
CLEANUP_INTERVAL = int(os.getenv('CLEANUP_INTERVAL', '60'))  # seconds
SEGMENT_RETENTION_TIME = int(os.getenv('SEGMENT_RETENTION_TIME', '300'))  # seconds (5 min)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format=f'[{NODE_ID}] %(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SegmentCleaner:
    """Manages cleanup of old IPFS segments"""
    
    def __init__(self):
        self.pinned_cids = set()
        self.load_pinned_cids()
    
    def load_pinned_cids(self):
        """Load list of pinned CIDs from IPFS"""
        try:
            response = requests.post(
                f'{IPFS_API}/api/v0/pin/ls',
                params={'type': 'recursive'},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'Keys' in data:
                    self.pinned_cids = set(data['Keys'].keys())
                    logger.info(f"Loaded {len(self.pinned_cids)} pinned CIDs")
            else:
                logger.error(f"Failed to load pinned CIDs: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Error loading pinned CIDs: {e}")
    
    def load_segment_state(self):
        """Load segment state from disk"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load segment state: {e}")
        return {}
    
    def save_segment_state(self, state):
        """Save segment state to disk"""
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save segment state: {e}")
    
    def unpin_cid(self, cid):
        """Unpin a CID from IPFS"""
        try:
            response = requests.post(
                f'{IPFS_API}/api/v0/pin/rm',
                params={'arg': cid},
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"✓ Unpinned: {cid}")
                self.pinned_cids.discard(cid)
                return True
            else:
                logger.error(f"Failed to unpin {cid}: {response.status_code}")
                return False
        
        except Exception as e:
            logger.error(f"Error unpinning {cid}: {e}")
            return False
    
    def delete_local_file(self, filename):
        """Delete local segment file"""
        try:
            filepath = os.path.join(HLS_DIR, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                logger.info(f"Deleted local file: {filename}")
                return True
        except Exception as e:
            logger.error(f"Error deleting {filename}: {e}")
        return False
    
    def cleanup_old_segments(self):
        """Remove old segments based on age and count"""
        state = self.load_segment_state()
        
        if not state:
            logger.debug("No segments to clean up")
            return
        
        current_time = int(time.time())
        total_removed = 0
        total_freed = 0
        
        for quality, segments in state.items():
            if not segments:
                continue
            
            logger.info(f"Checking {quality}: {len(segments)} segments")
            
            # Sort segments by timestamp
            sorted_segments = sorted(
                segments.items(),
                key=lambda x: x[1].get('timestamp', 0)
            )
            
            segments_to_remove = []
            
            # Remove segments older than retention time
            for filename, seg_info in sorted_segments:
                seg_time = seg_info.get('timestamp', 0)
                age = current_time - seg_time
                
                if age > SEGMENT_RETENTION_TIME:
                    segments_to_remove.append((filename, seg_info, 'age'))
            
            # Remove excess segments if we have more than MAX_SEGMENTS
            if len(sorted_segments) > MAX_SEGMENTS:
                excess_count = len(sorted_segments) - MAX_SEGMENTS
                for filename, seg_info in sorted_segments[:excess_count]:
                    if (filename, seg_info, 'age') not in [(f, s, r) for f, s, r in segments_to_remove]:
                        segments_to_remove.append((filename, seg_info, 'count'))
            
            # Remove identified segments
            for filename, seg_info, reason in segments_to_remove:
                cid = seg_info.get('cid')
                size = seg_info.get('size', 0)
                
                if cid:
                    # Unpin from IPFS
                    if self.unpin_cid(cid):
                        total_freed += size
                        total_removed += 1
                    
                    # Delete local file
                    self.delete_local_file(filename)
                    
                    # Remove from state
                    del segments[filename]
                    
                    logger.info(f"Removed {filename} (reason: {reason}, age: {current_time - seg_info.get('timestamp', 0)}s)")
        
        # Save updated state
        if total_removed > 0:
            self.save_segment_state(state)
            logger.info(f"Cleanup complete: removed {total_removed} segments, freed ~{total_freed / 1024 / 1024:.2f} MB")
        else:
            logger.debug("No segments needed cleanup")
    
    def garbage_collect(self):
        """Run IPFS garbage collection to free disk space"""
        try:
            logger.info("Running IPFS garbage collection...")
            response = requests.post(
                f'{IPFS_API}/api/v0/repo/gc',
                timeout=120
            )
            
            if response.status_code == 200:
                # Parse streaming response
                freed = 0
                for line in response.text.strip().split('\n'):
                    if line:
                        try:
                            obj = json.loads(line)
                            if 'Error' in obj:
                                logger.error(f"GC error: {obj['Error']}")
                        except json.JSONDecodeError:
                            pass
                
                logger.info("✓ Garbage collection complete")
            else:
                logger.error(f"GC failed: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Error during garbage collection: {e}")
    
    def get_storage_stats(self):
        """Get IPFS storage statistics"""
        try:
            response = requests.post(
                f'{IPFS_API}/api/v0/repo/stat',
                timeout=10
            )
            
            if response.status_code == 200:
                stats = response.json()
                repo_size = stats.get('RepoSize', 0) / 1024 / 1024  # MB
                storage_max = stats.get('StorageMax', 0) / 1024 / 1024  # MB
                num_objects = stats.get('NumObjects', 0)
                
                logger.info(f"Storage: {repo_size:.2f} MB / {storage_max:.2f} MB, Objects: {num_objects}")
                return stats
        
        except Exception as e:
            logger.error(f"Error getting storage stats: {e}")
        
        return None


def main():
    """Main entry point"""
    logger.info("Starting IPFS Segment Cleanup Service")
    logger.info(f"IPFS API: {IPFS_API}")
    logger.info(f"Max Segments: {MAX_SEGMENTS}")
    logger.info(f"Retention Time: {SEGMENT_RETENTION_TIME}s")
    logger.info(f"Cleanup Interval: {CLEANUP_INTERVAL}s")
    
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
    
    cleaner = SegmentCleaner()
    
    # Initial storage stats
    cleaner.get_storage_stats()
    
    gc_counter = 0
    gc_interval = 10  # Run GC every 10 cleanup cycles
    
    try:
        while True:
            logger.info("Running cleanup cycle...")
            
            # Cleanup old segments
            cleaner.cleanup_old_segments()
            
            # Run garbage collection periodically
            gc_counter += 1
            if gc_counter >= gc_interval:
                cleaner.garbage_collect()
                cleaner.get_storage_stats()
                gc_counter = 0
            
            # Wait for next cycle
            time.sleep(CLEANUP_INTERVAL)
    
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    
    logger.info("Service stopped")


if __name__ == '__main__':
    main()
