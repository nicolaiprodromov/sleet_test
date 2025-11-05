#!/usr/bin/env python3

import os
import sys
import json
import requests
import time

IPFS_API = os.getenv('IPFS_API', 'http://ipfs:5001')

def update_playlist(music_dir, playlist_data):
    try:
        manifest = playlist_data
        
        playlist_path = os.path.join(music_dir, 'playlist.m3u')
        
        with open(playlist_path, 'w') as f:
            for item in manifest:
                if 'path' in item:
                    f.write(f"{item['path']}\n")
                elif 'ipfs_hash' in item:
                    f.write(f"/ipfs/{item['ipfs_hash']}\n")
        
        print(f"Updated playlist: {playlist_path}")
        
        with open(playlist_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(f'{IPFS_API}/api/v0/add?pin=true', files=files)
            
            if response.status_code == 200:
                result = response.json()
                playlist_hash = result['Hash']
                print(f"Pinned playlist: {playlist_hash}")
                
                hash_file = os.path.join(music_dir, 'playlist_hash.txt')
                with open(hash_file, 'w') as f:
                    f.write(playlist_hash)
                
                return playlist_hash
        
        return None
        
    except Exception as e:
        print(f"Error updating playlist: {e}")
        return None

def fetch_remote_playlist(playlist_hash):
    try:
        response = requests.post(
            f'{IPFS_API}/api/v0/cat',
            params={'arg': playlist_hash},
            timeout=30
        )
        
        if response.status_code == 200:
            return response.text
        else:
            print(f"Error fetching playlist: {response.text}")
            return None
            
    except Exception as e:
        print(f"Exception fetching playlist: {e}")
        return None

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: update-playlist.py <manifest.json|playlist_hash>")
        sys.exit(1)
    
    target = sys.argv[1]
    music_dir = sys.argv[2] if len(sys.argv) > 2 else '/music'
    
    if os.path.exists(target):
        with open(target, 'r') as f:
            playlist_data = json.load(f)
        update_playlist(music_dir, playlist_data)
    
    else:
        content = fetch_remote_playlist(target)
        if content:
            playlist_path = os.path.join(music_dir, 'playlist.m3u')
            with open(playlist_path, 'w') as f:
                f.write(content)
            print(f"Updated playlist from IPFS: {target}")
