#!/usr/bin/env python3

import os
import sys
import json
import requests
import time
from pathlib import Path

IPFS_API = os.getenv('IPFS_API', 'http://ipfs:5001')
MUSIC_PIN = os.getenv('MUSIC_PIN', '')

def pin_ipfs_hash(ipfs_hash):
    try:
        response = requests.post(
            f'{IPFS_API}/api/v0/pin/add',
            params={'arg': ipfs_hash},
            timeout=300
        )
        
        if response.status_code == 200:
            print(f"Pinned: {ipfs_hash}")
            return True
        else:
            print(f"Error pinning {ipfs_hash}: {response.text}")
            return False
    except Exception as e:
        print(f"Exception pinning {ipfs_hash}: {e}")
        return False

def pin_from_manifest(manifest_path):
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        print(f"Pinning {len(manifest)} music files...")
        
        pinned = 0
        for item in manifest:
            if 'ipfs_hash' in item:
                if pin_ipfs_hash(item['ipfs_hash']):
                    pinned += 1
            
            if 'm3u8_hash' in item:
                if pin_ipfs_hash(item['m3u8_hash']):
                    pinned += 1
            
            time.sleep(0.5)
        
        print(f"Successfully pinned {pinned} items")
        return True
        
    except Exception as e:
        print(f"Error reading manifest: {e}")
        return False

def pin_directory(ipfs_dir_hash):
    try:
        print(f"Pinning directory: {ipfs_dir_hash}")
        
        response = requests.post(
            f'{IPFS_API}/api/v0/pin/add',
            params={'arg': ipfs_dir_hash, 'recursive': 'true'},
            timeout=600
        )
        
        if response.status_code == 200:
            print(f"Successfully pinned directory")
            return True
        else:
            print(f"Error: {response.text}")
            return False
            
    except Exception as e:
        print(f"Exception: {e}")
        return False

def wait_for_ipfs():
    print("Waiting for IPFS...")
    while True:
        try:
            response = requests.post(f'{IPFS_API}/api/v0/id', timeout=2)
            if response.status_code == 200:
                print("IPFS is ready")
                return True
        except:
            pass
        time.sleep(2)

if __name__ == '__main__':
    wait_for_ipfs()
    
    if len(sys.argv) > 1:
        target = sys.argv[1]
        
        if os.path.exists(target):
            pin_from_manifest(target)
        else:
            pin_ipfs_hash(target)
    
    elif MUSIC_PIN:
        pins = MUSIC_PIN.split(',')
        for pin in pins:
            pin = pin.strip()
            if pin:
                pin_ipfs_hash(pin)
    
    else:
        print("Usage: pin-music.py <manifest.json|ipfs_hash>")
        print("Or set MUSIC_PIN environment variable")
