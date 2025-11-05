#!/usr/bin/env python3
"""
IPNS-based IPFS Playlist Generator
Generates HLS m3u8 playlists with IPFS CIDs and publishes them to IPNS for mutable addressing.
This ensures the playlist URL remains constant while content continuously updates.
"""

import os
import sys
import json
import time
import requests
import logging
from pathlib import Path
from datetime import datetime

# Configuration
IPFS_API = os.getenv('IPFS_API', 'http://ipfs:5001')
IPFS_GATEWAY = os.getenv('IPFS_GATEWAY', 'http://ipfs:8080')
HLS_DIR = os.getenv('HLS_DIR', '/hls')
STATE_DIR = os.getenv('STATE_DIR', '/state')
STATE_FILE = os.path.join(STATE_DIR, 'ipfs_segments.json')
IPNS_STATE_FILE = os.path.join(STATE_DIR, 'ipns_keys.json')
NODE_ID = os.getenv('NODE_ID', 'node1')
UPDATE_INTERVAL = int(os.getenv('PLAYLIST_UPDATE_INTERVAL', '2'))  # seconds
SEGMENT_DURATION = 6  # seconds (must match liquidsoap config)
IPNS_LIFETIME = os.getenv('IPNS_LIFETIME', '24h')  # How long IPNS records are valid
IPNS_TTL = os.getenv('IPNS_TTL', '10s')  # Cache time for IPNS resolution
MAX_PLAYLIST_SEGMENTS = int(os.getenv('MAX_PLAYLIST_SEGMENTS', '15'))  # Segments in HLS playlist

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format=f'[{NODE_ID}] %(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IPNSManager:
    """Manages IPNS keys and publishing"""
    
    def __init__(self):
        self.keys = self.load_keys()
        self.ipfs_id = self.get_ipfs_id()
    
    def get_ipfs_id(self):
        """Get the IPFS node ID"""
        try:
            response = requests.post(f'{IPFS_API}/api/v0/id', timeout=5)
            if response.status_code == 200:
                return response.json()['ID']
        except Exception as e:
            logger.error(f"Failed to get IPFS ID: {e}")
        return None
    
    def load_keys(self):
        """Load IPNS keys from state"""
        if os.path.exists(IPNS_STATE_FILE):
            try:
                with open(IPNS_STATE_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load IPNS keys: {e}")
        return {}
    
    def save_keys(self):
        """Save IPNS keys to state"""
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(IPNS_STATE_FILE, 'w') as f:
                json.dump(self.keys, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save IPNS keys: {e}")
    
    def ensure_key(self, name):
        """Ensure an IPNS key exists, create if not"""
        if name in self.keys:
            return self.keys[name]
        
        try:
            # Check if key already exists in IPFS
            response = requests.post(
                f'{IPFS_API}/api/v0/key/list',
                timeout=5
            )
            
            if response.status_code == 200:
                existing_keys = response.json().get('Keys', [])
                for key in existing_keys:
                    if key['Name'] == name:
                        self.keys[name] = key['Id']
                        self.save_keys()
                        logger.info(f"Found existing IPNS key: {name} → {key['Id']}")
                        return key['Id']
            
            # Create new key
            response = requests.post(
                f'{IPFS_API}/api/v0/key/gen',
                params={'arg': name, 'type': 'ed25519'},
                timeout=10
            )
            
            if response.status_code == 200:
                key_id = response.json()['Id']
                self.keys[name] = key_id
                self.save_keys()
                logger.info(f"✓ Created IPNS key: {name} → {key_id}")
                return key_id
            else:
                logger.error(f"Failed to create key: {response.text}")
                return None
        
        except Exception as e:
            logger.error(f"Error ensuring key {name}: {e}")
            return None
    
    def publish(self, name, cid, allow_offline=True):
        """
        Publish a CID to an IPNS name
        
        Args:
            name: IPNS key name
            cid: Content identifier to publish
            allow_offline: Whether to publish even if not connected to network
        """
        try:
            params = {
                'arg': cid,
                'key': name,
                'lifetime': IPNS_LIFETIME,
                'ttl': IPNS_TTL,
                'resolve': 'true'
            }
            
            if allow_offline:
                params['allow-offline'] = 'true'
            
            response = requests.post(
                f'{IPFS_API}/api/v0/name/publish',
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                ipns_name = result.get('Name', result.get('name'))
                logger.info(f"✓ Published {name}: /ipns/{ipns_name} → /ipfs/{cid}")
                return ipns_name
            else:
                logger.error(f"IPNS publish failed: {response.status_code} - {response.text}")
                return None
        
        except Exception as e:
            logger.error(f"Error publishing to IPNS {name}: {e}")
            return None


class IPNSPlaylistGenerator:
    """Generates IPFS-based HLS playlists and publishes them to IPNS"""
    
    def __init__(self, ipns_manager):
        self.ipns = ipns_manager
        self.quality = 'stream'
        self.bandwidth = 200000
        self.codecs = 'mp4a.40.2'
        
        key_name = f'{NODE_ID}-stream'
        key_id = self.ipns.ensure_key(key_name)
        if key_id:
            self.stream_key = {'name': key_name, 'id': key_id}
        else:
            logger.error("Failed to initialize stream key!")
            self.stream_key = None
    
    def load_segments(self):
        """Load segment state from disk"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load segments: {e}")
        return {}
    
    def generate_media_playlist(self, quality, segments):
        """Generate a media playlist (quality-specific) for IPFS"""
        if not segments:
            logger.warning(f"No segments available for {quality}")
            return None
        
        # Get segment list (sorted by timestamp)
        segment_list = sorted(segments.items(), key=lambda x: x[1]['timestamp'])
        
        # Take only the last N segments for the live stream
        segment_list = segment_list[-MAX_PLAYLIST_SEGMENTS:]
        
        if not segment_list:
            return None
        
        # Calculate sequence number (for HLS continuity)
        first_segment = segment_list[0]
        sequence_num = self.extract_sequence_from_filename(first_segment[0])
        
        # Build M3U8 content
        lines = [
            '#EXTM3U',
            '#EXT-X-VERSION:3',
            f'#EXT-X-TARGETDURATION:{SEGMENT_DURATION + 1}',
            f'#EXT-X-MEDIA-SEQUENCE:{sequence_num}',
        ]
        
        # Add segments with IPFS gateway URLs
        for filename, seg_info in segment_list:
            cid = seg_info['cid']
            lines.append(f'#EXTINF:{SEGMENT_DURATION}.0,')
            # Use relative path for gateway resolution
            lines.append(f'/ipfs/{cid}')
        
        return '\n'.join(lines) + '\n'
    
    def generate_master_playlist(self, stream_ipns):
        """Generate master playlist with IPNS link to stream"""
        lines = [
            '#EXTM3U',
            '#EXT-X-VERSION:3',
            f'#EXT-X-STREAM-INF:BANDWIDTH={self.bandwidth},'
            f'CODECS="{self.codecs}"',
            f'/ipns/{stream_ipns}'
        ]
        
        return '\n'.join(lines) + '\n'
    
    def extract_sequence_from_filename(self, filename):
        """Extract sequence number from segment filename"""
        # Format: {quality}_{duration}_{timestamp}_{position}.ts
        parts = filename.replace('.ts', '').split('_')
        if len(parts) >= 4:
            try:
                return int(parts[3])
            except ValueError:
                pass
        return 0
    
    def upload_to_ipfs(self, content, filename):
        """Upload content to IPFS and return CID"""
        try:
            files = {'file': (filename, content.encode('utf-8'))}
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
                logger.error(f"IPFS API error: {response.status_code}")
                return None
        
        except Exception as e:
            logger.error(f"Upload error: {e}")
            return None
    
    def update_playlists(self):
        """Update all playlists with current segment state and publish to IPNS"""
        segments = self.load_segments()
        
        if not segments:
            logger.debug("No segments to process")
            return False
        
        stream_segments = segments.get('stream', {})
        if not stream_segments or not self.stream_key:
            logger.debug("No stream segments available")
            return False
        
        playlist_content = self.generate_media_playlist('stream', stream_segments)
        
        if not playlist_content:
            return False
        
        playlist_cid = self.upload_to_ipfs(playlist_content, 'stream.m3u8')
        
        if not playlist_cid:
            return False
        
        key_name = self.stream_key['name']
        stream_ipns = self.ipns.publish(key_name, playlist_cid)
        
        if not stream_ipns:
            return False
        
        logger.info(f"✓ Stream playlist published to IPNS: /ipns/{stream_ipns}")
        
        local_path = os.path.join(HLS_DIR, 'stream_ipfs.m3u8')
        try:
            with open(local_path, 'w') as f:
                f.write(playlist_content)
        except Exception as e:
            logger.error(f"Failed to write local playlist: {e}")
        
        master_content = self.generate_master_playlist(stream_ipns)
        master_cid = self.upload_to_ipfs(master_content, 'master.m3u8')
        
        if master_cid:
            master_key_name = f'{NODE_ID}-master'
            self.ipns.ensure_key(master_key_name)
            master_ipns = self.ipns.publish(master_key_name, master_cid)
            
            if master_ipns:
                logger.info(f"✓ Master playlist published to IPNS: /ipns/{master_ipns}")
                
                self.write_stream_info(master_ipns, stream_ipns)
                
                local_path = os.path.join(HLS_DIR, 'master_ipfs.m3u8')
                try:
                    with open(local_path, 'w') as f:
                        f.write(master_content)
                except Exception as e:
                    logger.error(f"Failed to write local master playlist: {e}")
        
        return True
    
    def write_stream_info(self, master_ipns, stream_ipns):
        """Write stream information file with IPNS URLs"""
        info = {
            'master_playlist_ipns': master_ipns,
            'master_playlist_url': f'{IPFS_GATEWAY}/ipns/{master_ipns}',
            'stream_playlist_ipns': stream_ipns,
            'stream_playlist_url': f'{IPFS_GATEWAY}/ipns/{stream_ipns}',
            'bitrate': '192k',
            'bandwidth': self.bandwidth,
            'updated_at': datetime.utcnow().isoformat(),
            'node_id': NODE_ID,
            'info': 'This stream uses IPNS for mutable addressing. URLs remain constant while content updates.'
        }
        
        try:
            stream_info_path = os.path.join(STATE_DIR, 'stream_info.json')
            with open(stream_info_path, 'w') as f:
                json.dump(info, f, indent=2)
            
            logger.debug(f"Stream info updated: {stream_info_path}")
        
        except Exception as e:
            logger.error(f"Failed to write stream info: {e}")


def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("IPNS-based IPFS Playlist Generator Service")
    logger.info("=" * 60)
    logger.info(f"IPFS API: {IPFS_API}")
    logger.info(f"IPFS Gateway: {IPFS_GATEWAY}")
    logger.info(f"Update Interval: {UPDATE_INTERVAL}s")
    logger.info(f"IPNS Lifetime: {IPNS_LIFETIME}")
    logger.info(f"IPNS TTL: {IPNS_TTL}")
    
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
    
    # Initialize IPNS manager and playlist generator
    ipns_manager = IPNSManager()
    generator = IPNSPlaylistGenerator(ipns_manager)
    
    logger.info("=" * 60)
    logger.info("Starting playlist update loop...")
    logger.info("Playlists will be continuously updated and published to IPNS")
    logger.info("=" * 60)
    
    try:
        iteration = 0
        while True:
            iteration += 1
            try:
                updated = generator.update_playlists()
                if updated:
                    logger.info(f"[Iteration {iteration}] ✓ Playlists updated")
                else:
                    logger.debug(f"[Iteration {iteration}] No changes detected")
            except Exception as e:
                logger.error(f"Error updating playlists: {e}", exc_info=True)
            
            time.sleep(UPDATE_INTERVAL)
    
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    
    logger.info("Service stopped")


if __name__ == '__main__':
    main()
