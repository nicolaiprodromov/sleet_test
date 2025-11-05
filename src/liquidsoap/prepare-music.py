#!/usr/bin/env python3

import os
import sys
import json
import requests
import time

IPFS_API = os.getenv('IPFS_API', 'http://ipfs:5001')
MUSIC_DIR = '/music'

def process_music_file(file_path, output_dir):
    try:
        print(f"Processing: {file_path}")
        
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(f'{IPFS_API}/api/v0/add?pin=true', files=files)
            
            if response.status_code == 200:
                result = response.json()
                hash_value = result['Hash']
                print(f"Pinned {file_path}: {hash_value}")
                
                metadata = {
                    'filename': os.path.basename(file_path),
                    'ipfs_hash': hash_value,
                    'size': result['Size'],
                    'path': file_path,
                    'timestamp': int(time.time())
                }
                
                return metadata
            else:
                print(f"Error: {response.text}")
                return None
    except Exception as e:
        print(f"Exception: {e}")
        return None

def create_pre_chunked_hls(music_files, output_dir):
    import subprocess
    
    os.makedirs(output_dir, exist_ok=True)
    
    for idx, music_file in enumerate(music_files):
        try:
            base_name = os.path.splitext(os.path.basename(music_file['path']))[0]
            chunk_dir = os.path.join(output_dir, f"track_{idx:03d}")
            os.makedirs(chunk_dir, exist_ok=True)
            
            m3u8_file = os.path.join(chunk_dir, f"{base_name}.m3u8")
            
            cmd = [
                'ffmpeg', '-i', music_file['path'],
                '-c:a', 'aac', '-b:a', '128k',
                '-f', 'hls',
                '-hls_time', '6',
                '-hls_list_size', '0',
                '-hls_segment_filename', os.path.join(chunk_dir, f"{base_name}_%03d.ts"),
                m3u8_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"Created HLS chunks for {base_name}")
                
                for file in os.listdir(chunk_dir):
                    if file.endswith('.ts'):
                        chunk_path = os.path.join(chunk_dir, file)
                        with open(chunk_path, 'rb') as f:
                            files = {'file': f}
                            response = requests.post(f'{IPFS_API}/api/v0/add?pin=true', files=files)
                            if response.status_code == 200:
                                chunk_hash = response.json()['Hash']
                                print(f"  Pinned chunk: {file} -> {chunk_hash}")
                
                with open(m3u8_file, 'rb') as f:
                    files = {'file': f}
                    response = requests.post(f'{IPFS_API}/api/v0/add?pin=true', files=files)
                    if response.status_code == 200:
                        m3u8_hash = response.json()['Hash']
                        music_file['m3u8_hash'] = m3u8_hash
                        print(f"  Pinned m3u8: {m3u8_hash}")
            else:
                print(f"Error creating HLS: {result.stderr}")
                
        except Exception as e:
            print(f"Exception processing {music_file['path']}: {e}")

def scan_and_pin_music(music_dir, output_dir):
    music_files = []
    
    for root, dirs, files in os.walk(music_dir):
        for file in files:
            if file.endswith(('.mp3', '.flac', '.wav', '.ogg', '.m4a')):
                file_path = os.path.join(root, file)
                metadata = process_music_file(file_path, output_dir)
                if metadata:
                    music_files.append(metadata)
    
    print(f"\nProcessed {len(music_files)} music files")
    
    print("\nCreating pre-chunked HLS files...")
    create_pre_chunked_hls(music_files, output_dir)
    
    manifest_file = os.path.join(output_dir, 'music_manifest.json')
    with open(manifest_file, 'w') as f:
        json.dump(music_files, f, indent=2)
    
    print(f"\nManifest saved to: {manifest_file}")
    
    return music_files

if __name__ == '__main__':
    music_dir = sys.argv[1] if len(sys.argv) > 1 else MUSIC_DIR
    output_dir = sys.argv[2] if len(sys.argv) > 2 else '/data/processed'
    
    print(f"Scanning music directory: {music_dir}")
    music_files = scan_and_pin_music(music_dir, output_dir)
    print(f"\nTotal files pinned: {len(music_files)}")
