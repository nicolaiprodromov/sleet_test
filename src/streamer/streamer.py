#!/usr/bin/env python3

import os
import sys
import json
import time
import requests
import logging
from pathlib import Path
from datetime import datetime, timedelta

IPFS_API = os.getenv('IPFS_API', 'http://ipfs:5001')
IPFS_GATEWAY = os.getenv('IPFS_GATEWAY', 'http://ipfs:8080')
STATE_DIR = os.getenv('STATE_DIR', '/state')
PROCESSED_DIR = os.getenv('PROCESSED_DIR', '/data/processed')
NODE_ID = os.getenv('NODE_ID', 'node1')

MANIFEST_FILE = os.path.join(PROCESSED_DIR, 'manifest.json')
PLAYLIST_FILE = os.path.join(STATE_DIR, 'playlist.m3u')
IPNS_STATE_FILE = os.path.join(STATE_DIR, 'ipns_keys.json')
CONFIG_FILE = os.getenv('STREAMING_CONFIG', '/workspace/streaming.config.json')

logging.basicConfig(
    level=logging.INFO,
    format=f'[{NODE_ID}] %(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StreamingConfig:
    def __init__(self, config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        self.window_size = config['streaming']['window_size']
        self.update_interval = config['streaming']['update_interval']
        self.max_segments = config['streaming']['max_segments']
        self.advance_every = config['streaming'].get('advance_every', 2)
        
        self.ipns_lifetime = config['ipns']['lifetime']
        self.ipns_ttl = config['ipns']['ttl']
        self.ipns_allow_offline = config['ipns']['allow_offline']
        
        logger.info(f"Loaded streaming config: window_size={self.window_size}, "
                   f"update_interval={self.update_interval}s, "
                   f"max_segments={self.max_segments}, "
                   f"advance_every={self.advance_every}")


class IPNSManager:
    def __init__(self):
        self.keys = self.load_keys()
        self.ipfs_id = self.get_ipfs_id()
    
    def get_ipfs_id(self):
        try:
            response = requests.post(f'{IPFS_API}/api/v0/id', timeout=5)
            if response.status_code == 200:
                return response.json()['ID']
        except Exception as e:
            logger.error(f"Failed to get IPFS ID: {e}")
        return None
    
    def load_keys(self):
        if os.path.exists(IPNS_STATE_FILE):
            try:
                with open(IPNS_STATE_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load IPNS keys: {e}")
        return {}
    
    def save_keys(self):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(IPNS_STATE_FILE, 'w') as f:
                json.dump(self.keys, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save IPNS keys: {e}")
    
    def ensure_key(self, name):
        if name in self.keys:
            return self.keys[name]
        
        try:
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
    
    def publish(self, name, cid, lifetime, ttl, allow_offline=True):
        try:
            params = {
                'arg': cid,
                'key': name,
                'lifetime': lifetime,
                'ttl': ttl,
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


class SlidingWindowStreamer:
    def __init__(self, config, ipns_manager):
        self.config = config
        self.ipns = ipns_manager
        
        self.manifest = self.load_manifest()
        self.playlist_entries = self.load_playlist()
        
        self.sequence_state_file = os.path.join(STATE_DIR, 'sequence_state.json')
        state = self.load_sequence_state()
        self.sequence_number = state['sequence']
        self.update_counter = 0
        
        key_name = f'{NODE_ID}-stream'
        key_id = self.ipns.ensure_key(key_name)
        if key_id:
            self.stream_key = {'name': key_name, 'id': key_id}
        else:
            logger.error("Failed to initialize stream key!")
            self.stream_key = None
    
    def load_manifest(self):
        try:
            with open(MANIFEST_FILE, 'r') as f:
                manifest = json.load(f)
            logger.info(f"✓ Loaded manifest with {len(manifest['tracks'])} tracks")
            return manifest
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")
            sys.exit(1)
    
    def load_playlist(self):
        entries = []
        try:
            with open(PLAYLIST_FILE, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('/ipfs/'):
                        cid = line.replace('/ipfs/', '')
                        entries.append(cid)
            logger.info(f"✓ Loaded playlist with {len(entries)} segments")
            return entries
        except Exception as e:
            logger.error(f"Failed to load playlist: {e}")
            sys.exit(1)
    
    def load_sequence_state(self):
        if os.path.exists(self.sequence_state_file):
            try:
                with open(self.sequence_state_file, 'r') as f:
                    state = json.load(f)
                logger.info(f"✓ Restored sequence state: sequence={state['sequence']}")
                return state
            except Exception as e:
                logger.warning(f"Failed to load sequence state: {e}, starting fresh")
        
        return {'sequence': 0}
    
    def save_sequence_state(self):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            state = {
                'sequence': self.sequence_number,
                'timestamp': datetime.utcnow().isoformat()
            }
            with open(self.sequence_state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save sequence state: {e}")
    
    def get_window_segments(self):
        total_segments = len(self.playlist_entries)
        if total_segments == 0:
            return []
        
        window_segments = []
        current_position = self.sequence_number % total_segments
        
        for i in range(self.config.max_segments):
            playlist_index = (current_position + i) % total_segments
            window_segments.append(self.playlist_entries[playlist_index])
        
        return window_segments
    
    def advance_window(self):
        total_segments = len(self.playlist_entries)
        if total_segments == 0:
            return
        
        self.update_counter += 1
        
        if self.update_counter >= self.config.advance_every:
            self.sequence_number += 1
            self.update_counter = 0
            self.save_sequence_state()
            current_playlist_pos = self.sequence_number % total_segments
            logger.debug(f"Stream advanced - sequence: {self.sequence_number}, playlist position: {current_playlist_pos}")
        else:
            logger.debug(f"Playlist refreshed (no advance, counter: {self.update_counter})")
    
    def generate_hls_playlist(self, segments):
        if not segments:
            return None
        
        current_time = datetime.utcnow()
        
        lines = [
            '#EXTM3U',
            '#EXT-X-VERSION:3',
            '#EXT-X-TARGETDURATION:7',
            f'#EXT-X-MEDIA-SEQUENCE:{self.sequence_number}',
        ]
        
        for i, cid in enumerate(segments):
            segment_time = current_time - timedelta(seconds=(len(segments) - i - 1) * 6)
            lines.append(f'#EXT-X-PROGRAM-DATE-TIME:{segment_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]}Z')
            lines.append('#EXTINF:6.0,')
            lines.append(f'/ipfs/{cid}')
        
        return '\n'.join(lines) + '\n'
    
    def upload_to_ipfs(self, content, filename):
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
    
    def update_stream(self):
        if not self.stream_key:
            return False
        
        window_segments = self.get_window_segments()
        if not window_segments:
            logger.error("No segments in window")
            return False
        
        playlist_content = self.generate_hls_playlist(window_segments)
        if not playlist_content:
            return False
        
        playlist_cid = self.upload_to_ipfs(playlist_content, 'stream.m3u8')
        if not playlist_cid:
            return False
        
        stream_ipns = self.ipns.publish(
            self.stream_key['name'],
            playlist_cid,
            self.config.ipns_lifetime,
            self.config.ipns_ttl,
            self.config.ipns_allow_offline
        )
        
        if not stream_ipns:
            return False
        
        self.write_stream_info(stream_ipns)
        self.advance_window()
        
        return True
    
    def write_stream_info(self, stream_ipns):
        current_playlist_pos = self.sequence_number % len(self.playlist_entries)
        info = {
            'stream_playlist_ipns': stream_ipns,
            'stream_playlist_url': f'{IPFS_GATEWAY}/ipns/{stream_ipns}',
            'sequence_number': self.sequence_number,
            'playlist_position': current_playlist_pos,
            'updated_at': datetime.utcnow().isoformat(),
            'node_id': NODE_ID,
        }
        
        try:
            stream_info_path = os.path.join(STATE_DIR, 'stream_info.json')
            with open(stream_info_path, 'w') as f:
                json.dump(info, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write stream info: {e}")


def main():
    logger.info("=" * 60)
    logger.info("Sleetbubble IPFS Streaming Service")
    logger.info("=" * 60)
    logger.info(f"IPFS API: {IPFS_API}")
    logger.info(f"IPFS Gateway: {IPFS_GATEWAY}")
    
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
    
    config = StreamingConfig(CONFIG_FILE)
    ipns_manager = IPNSManager()
    streamer = SlidingWindowStreamer(config, ipns_manager)
    
    logger.info("=" * 60)
    logger.info("Starting streaming loop...")
    logger.info(f"Window will advance every {config.update_interval}s")
    logger.info("=" * 60)
    
    try:
        iteration = 0
        while True:
            iteration += 1
            try:
                updated = streamer.update_stream()
                if updated:
                    playlist_pos = streamer.sequence_number % len(streamer.playlist_entries)
                    logger.info(f"[Iteration {iteration}] ✓ Stream updated - "
                              f"sequence: {streamer.sequence_number}, "
                              f"playlist position: {playlist_pos}")
                else:
                    logger.error(f"[Iteration {iteration}] Failed to update stream")
            except Exception as e:
                logger.error(f"Error updating stream: {e}", exc_info=True)
            
            time.sleep(config.update_interval)
    
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    
    logger.info("Service stopped")


if __name__ == '__main__':
    main()
