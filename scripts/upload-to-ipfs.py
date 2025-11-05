#!/usr/bin/env python3

import os
import sys
import json
import requests
import time
from pathlib import Path

IPFS_API = os.getenv('IPFS_API', 'http://ipfs:5001')
HLS_DIR = '/hls'

def add_to_ipfs(file_path):
    try:
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(f'{IPFS_API}/api/v0/add?pin=true', files=files)
            
            if response.status_code == 200:
                result = response.json()
                hash_value = result['Hash']
                print(f"Added {file_path} to IPFS: {hash_value}")
                
                log_entry = {
                    'file': os.path.basename(file_path),
                    'hash': hash_value,
                    'timestamp': int(time.time())
                }
                
                log_file = os.path.join(HLS_DIR, 'ipfs_hashes.log')
                with open(log_file, 'a') as log:
                    log.write(json.dumps(log_entry) + '\n')
                
                return hash_value
            else:
                print(f"Error adding to IPFS: {response.text}")
                return None
    except Exception as e:
        print(f"Exception adding to IPFS: {e}")
        return None

def update_m3u8_with_ipfs(m3u8_path):
    try:
        if not os.path.exists(m3u8_path):
            return
        
        with open(m3u8_path, 'r') as f:
            lines = f.readlines()
        
        log_file = os.path.join(HLS_DIR, 'ipfs_hashes.log')
        if not os.path.exists(log_file):
            return
        
        hashes = {}
        with open(log_file, 'r') as log:
            for line in log:
                if line.strip():
                    entry = json.loads(line)
                    hashes[entry['file']] = entry['hash']
        
        new_lines = []
        for line in lines:
            if line.strip().endswith('.ts'):
                filename = os.path.basename(line.strip())
                if filename in hashes:
                    ipfs_hash = hashes[filename]
                    new_lines.append(f"/ipfs/{ipfs_hash}\n")
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        ipfs_m3u8_path = m3u8_path.replace('.m3u8', '_ipfs.m3u8')
        with open(ipfs_m3u8_path, 'w') as f:
            f.writelines(new_lines)
        
        add_to_ipfs(ipfs_m3u8_path)
        
    except Exception as e:
        print(f"Exception updating m3u8: {e}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: upload-to-ipfs.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        sys.exit(1)
    
    add_to_ipfs(file_path)
    
    if file_path.endswith('.m3u8'):
        update_m3u8_with_ipfs(file_path)
