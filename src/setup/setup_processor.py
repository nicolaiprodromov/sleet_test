#!/usr/bin/env python3

import os
import sys
import json
import hashlib
import subprocess
import requests
import time
from pathlib import Path

IPFS_API = os.getenv('IPFS_API', 'http://ipfs:5001')

class SetupProcessor:
    def __init__(self, workspace_dir='/workspace', processed_dir='/data/processed', state_dir='/state'):
        self.workspace_dir = Path(workspace_dir)
        self.processed_dir = Path(processed_dir)
        self.state_dir = Path(state_dir)
        
        self.setup_config = self.load_setup_config()
        self.playlist_config = self.load_playlist_config()
        
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
    def load_setup_config(self):
        config_path = self.workspace_dir / 'setup.config.json'
        if not config_path.exists():
            print(f"ERROR: setup.config.json not found at {config_path}")
            sys.exit(1)
        
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def load_playlist_config(self):
        config_path = self.workspace_dir / 'playlist.config.json'
        if not config_path.exists():
            print(f"WARNING: playlist.config.json not found at {config_path}")
            return {}
        
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def compute_config_hash(self):
        config_str = json.dumps({
            'setup': self.setup_config,
            'playlist': self.playlist_config
        }, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()
    
    def load_manifest(self):
        manifest_path = self.processed_dir / 'manifest.json'
        if manifest_path.exists():
            with open(manifest_path, 'r') as f:
                return json.load(f)
        return None
    
    def needs_rebuild(self):
        if self.setup_config.get('processing', {}).get('force_rebuild', False):
            print("Force rebuild enabled in config")
            return True
        
        manifest = self.load_manifest()
        if not manifest:
            print("No existing manifest found")
            return True
        
        current_hash = self.compute_config_hash()
        stored_hash = manifest.get('config_hash')
        
        if current_hash != stored_hash:
            print(f"Config changed (hash mismatch)")
            return True
        
        print("Cache valid, skipping rebuild")
        return False
    
    def get_music_files(self):
        source = self.playlist_config.get('source', '')
        if not source:
            print("WARNING: No source specified in playlist.config.json")
            return []
        
        source_path = self.workspace_dir / source
        if not source_path.exists():
            print(f"ERROR: Source path {source_path} does not exist")
            return []
        
        tracks = self.playlist_config.get('tracks', [])
        options = self.playlist_config.get('options', {})
        scan_subdirs = options.get('scan_subdirectories', True)
        
        music_files = []
        audio_extensions = {'.mp3', '.flac', '.wav', '.ogg', '.m4a'}
        
        if tracks:
            print(f"Processing {len(tracks)} specified tracks from playlist.config.json")
            for track in tracks:
                track_path = source_path / track
                if not track_path.exists() and scan_subdirs:
                    found = list(source_path.rglob(track))
                    if found:
                        track_path = found[0]
                
                if track_path.exists():
                    music_files.append(track_path)
                else:
                    print(f"WARNING: Track not found: {track}")
            
            return music_files
        else:
            print(f"No tracks specified, scanning all audio files in {source_path}")
            if scan_subdirs:
                for ext in audio_extensions:
                    music_files.extend(source_path.rglob(f'*{ext}'))
            else:
                for file in source_path.iterdir():
                    if file.is_file() and file.suffix.lower() in audio_extensions:
                        music_files.append(file)
            
            return sorted(music_files)
    
    def get_jingle_files(self):
        if not self.setup_config.get('jingles', {}).get('enabled', False):
            print("Jingles disabled in config")
            return []
        
        jingles_source = self.setup_config['jingles'].get('source', 'src/jingles')
        jingles_path = self.workspace_dir / jingles_source
        
        if not jingles_path.exists():
            print(f"WARNING: Jingles directory {jingles_path} does not exist")
            return []
        
        audio_extensions = {'.mp3', '.flac', '.wav', '.ogg', '.m4a'}
        jingles = [f for f in jingles_path.iterdir() 
                   if f.is_file() and f.suffix.lower() in audio_extensions]
        
        return sorted(jingles)
    
    def verify_audio_file(self, audio_file):
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(audio_file)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return None, f"ffprobe failed: {result.stderr}"
        
        try:
            duration = float(result.stdout.strip())
            if duration < 0.1:
                return None, f"Duration too short: {duration}s"
            return duration, None
        except ValueError:
            return None, "Could not parse duration"
    
    def chunk_audio_file(self, audio_file, output_dir, file_type='track'):
        base_name = audio_file.stem
        output_dir.mkdir(parents=True, exist_ok=True)
        
        segment_filename = output_dir / f"{base_name}_%03d.ts"
        m3u8_file = output_dir / f"{base_name}.m3u8"
        
        audio_config = self.setup_config.get('audio', {})
        segment_duration = audio_config.get('segment_duration', 6)
        bitrate = audio_config.get('bitrate', '128k')
        codec = audio_config.get('codec', 'aac')
        
        cmd = [
            'ffmpeg', '-i', str(audio_file),
            '-vn',
            '-c:a', codec, '-b:a', bitrate,
            '-f', 'hls',
            '-hls_time', str(segment_duration),
            '-hls_list_size', '0',
            '-hls_segment_type', 'mpegts',
            '-force_key_frames', f'expr:gte(t,n_forced*{segment_duration})',
            '-hls_segment_filename', str(segment_filename),
            str(m3u8_file)
        ]
        
        print(f"  Chunking {audio_file.name}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"  ERROR: FFmpeg failed for {audio_file.name}")
            print(f"  STDERR: {result.stderr}")
            return None
        
        if result.stderr:
            print(f"  WARNING: {result.stderr}")
        
        segments = sorted(output_dir.glob(f"{base_name}_*.ts"))
        
        if len(segments) == 0:
            print(f"  ERROR: No segments created for {audio_file.name}")
            return None
        
        if len(segments) == 1:
            segment_size_mb = segments[0].stat().st_size / (1024 * 1024)
            if segment_size_mb > 1.0:
                print(f"  WARNING: Only 1 segment created ({segment_size_mb:.1f}MB) - file may not have been properly segmented")
                print(f"  This usually means FFmpeg couldn't decode the audio properly")
        
        print(f"  Created {len(segments)} segments")
        
        return {
            'filename': audio_file.name,
            'type': file_type,
            'base_name': base_name,
            'segments': [s.name for s in segments],
            'segment_count': len(segments),
            'output_dir': str(output_dir.relative_to(self.processed_dir))
        }
    
    def upload_to_ipfs(self, file_path):
        ipfs_config = self.setup_config.get('ipfs', {})
        timeout = ipfs_config.get('timeout', 30)
        pin = ipfs_config.get('pin_segments', True)
        
        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                response = requests.post(
                    f'{IPFS_API}/api/v0/add?pin={str(pin).lower()}',
                    files=files,
                    timeout=timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result['Hash']
                else:
                    print(f"  ERROR: IPFS upload failed for {file_path.name}: {response.text}")
                    return None
        except Exception as e:
            print(f"  ERROR: Exception uploading {file_path.name}: {e}")
            return None
    
    def process_track(self, track_file, track_index, file_type='track'):
        duration, error = self.verify_audio_file(track_file)
        
        if error:
            print(f"  ERROR: Cannot process {track_file.name}: {error}")
            return None
        
        print(f"  Duration: {duration:.1f}s")
        
        track_dir = self.processed_dir / f"{file_type}_{track_index:03d}"
        
        chunk_info = self.chunk_audio_file(track_file, track_dir, file_type)
        if not chunk_info:
            return None
        
        print(f"  Uploading segments to IPFS...")
        segment_cids = []
        
        for segment_name in chunk_info['segments']:
            segment_path = track_dir / segment_name
            cid = self.upload_to_ipfs(segment_path)
            if cid:
                segment_cids.append({
                    'filename': segment_name,
                    'cid': cid
                })
                print(f"    {segment_name} -> {cid}")
            else:
                print(f"    Failed to upload {segment_name}")
                return None
        
        return {
            'filename': chunk_info['filename'],
            'type': file_type,
            'base_name': chunk_info['base_name'],
            'segment_count': chunk_info['segment_count'],
            'segments': segment_cids,
            'output_dir': chunk_info['output_dir']
        }
    
    def build_playlist(self, tracks, jingles):
        playlist_lines = ['#EXTM3U']
        
        jingles_enabled = self.setup_config.get('jingles', {}).get('enabled', False)
        jingle_cycle = self.setup_config.get('jingles', {}).get('cycle', 2)
        
        if not jingles_enabled or not jingles:
            for track in tracks:
                for segment in track['segments']:
                    playlist_lines.append(f"#EXTINF:{self.setup_config['audio']['segment_duration']},")
                    playlist_lines.append(f"/ipfs/{segment['cid']}")
        else:
            track_counter = 0
            jingle_index = 0
            
            for track in tracks:
                if track_counter > 0 and track_counter % jingle_cycle == 0:
                    jingle = jingles[jingle_index % len(jingles)]
                    for segment in jingle['segments']:
                        playlist_lines.append(f"#EXTINF:{self.setup_config['audio']['segment_duration']},")
                        playlist_lines.append(f"/ipfs/{segment['cid']}")
                    jingle_index += 1
                
                for segment in track['segments']:
                    playlist_lines.append(f"#EXTINF:{self.setup_config['audio']['segment_duration']},")
                    playlist_lines.append(f"/ipfs/{segment['cid']}")
                
                track_counter += 1
        
        return '\n'.join(playlist_lines) + '\n'
    
    def run(self):
        print("=================================")
        print("SleetBubble Setup Processor")
        print("=================================")
        print()
        
        if not self.needs_rebuild():
            print("✓ Setup already complete and up-to-date")
            manifest = self.load_manifest()
            if manifest:
                print("\n--- Regenerating Playlist from Manifest ---")
                playlist_content = self.build_playlist(manifest['tracks'], manifest.get('jingles', []))
                playlist_path = self.state_dir / 'playlist.m3u'
                with open(playlist_path, 'w') as f:
                    f.write(playlist_content)
                print(f"✓ Playlist regenerated at {playlist_path}")
            return
        
        print("\n--- Processing Music Files ---")
        music_files = self.get_music_files()
        if not music_files:
            print("ERROR: No music files found")
            sys.exit(1)
        
        print(f"Found {len(music_files)} music files")
        
        processed_tracks = []
        for idx, track_file in enumerate(music_files):
            print(f"\nProcessing track {idx + 1}/{len(music_files)}: {track_file.name}")
            track_data = self.process_track(track_file, idx, 'track')
            if track_data:
                processed_tracks.append(track_data)
            else:
                print(f"ERROR: Failed to process {track_file.name}")
                sys.exit(1)
        
        print("\n--- Processing Jingles ---")
        jingle_files = self.get_jingle_files()
        processed_jingles = []
        
        if jingle_files:
            print(f"Found {len(jingle_files)} jingle files")
            for idx, jingle_file in enumerate(jingle_files):
                print(f"\nProcessing jingle {idx + 1}/{len(jingle_files)}: {jingle_file.name}")
                jingle_data = self.process_track(jingle_file, idx, 'jingle')
                if jingle_data:
                    processed_jingles.append(jingle_data)
                else:
                    print(f"WARNING: Failed to process jingle {jingle_file.name}")
        else:
            print("No jingles to process")
        
        print("\n--- Building Playlist ---")
        playlist_content = self.build_playlist(processed_tracks, processed_jingles)
        
        playlist_path = self.state_dir / 'playlist.m3u'
        with open(playlist_path, 'w') as f:
            f.write(playlist_content)
        print(f"✓ Playlist saved to {playlist_path}")
        
        print("\n--- Generating Manifest ---")
        manifest = {
            'config_hash': self.compute_config_hash(),
            'timestamp': int(time.time()),
            'tracks': processed_tracks,
            'jingles': processed_jingles,
            'audio_config': self.setup_config.get('audio', {}),
            'jingles_config': self.setup_config.get('jingles', {})
        }
        
        manifest_path = self.processed_dir / 'manifest.json'
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        print(f"✓ Manifest saved to {manifest_path}")
        
        print("\n=================================")
        print("Setup Complete!")
        print(f"Processed {len(processed_tracks)} tracks")
        print(f"Processed {len(processed_jingles)} jingles")
        total_segments = sum(t['segment_count'] for t in processed_tracks)
        total_segments += sum(j['segment_count'] for j in processed_jingles)
        print(f"Total segments: {total_segments}")
        print("=================================")

if __name__ == '__main__':
    processor = SetupProcessor()
    processor.run()
