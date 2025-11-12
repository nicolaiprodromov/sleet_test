#!/usr/bin/env python3
# inspired by https://github.com/meehow/peer-id-generator
import sys
import time
import base64
import requests
import subprocess
from pathlib import Path

IPFS_API = 'http://localhost:5001'

def generate_vanity_key(substring, max_attempts=100000, position='anywhere'):
    position_text = {
        'anywhere': f"containing '{substring}'",
        'start': f"starting with '{substring}'",
        'end': f"ending with '{substring}'"
    }
    print(f"Searching for IPNS key {position_text.get(position, position_text['anywhere'])}...")
    print(f"This may take a while. Press Ctrl+C to stop.\n")
    
    start_time = time.time()
    attempts = 0
    found_keys = []
    
    try:
        while attempts < max_attempts:
            attempts += 1
            
            temp_key_name = f'temp_vanity_{attempts}'
            
            try:
                response = requests.post(
                    f'{IPFS_API}/api/v0/key/gen',
                    params={'arg': temp_key_name, 'type': 'ed25519'},
                    timeout=5
                )
                
                if response.status_code != 200:
                    print(f"Error generating key: {response.text}")
                    continue
                
                key_data = response.json()
                key_id = key_data['Id']
                key_lower = key_id.lower()
                substring_lower = substring.lower()
                
                match_found = False
                if position == 'start':
                    match_found = key_lower.startswith(substring_lower)
                elif position == 'end':
                    match_found = key_lower.endswith(substring_lower)
                else:
                    match_found = substring_lower in key_lower
                
                if match_found:
                    elapsed = time.time() - start_time
                    print(f"\n✓ FOUND! (attempt #{attempts}, {elapsed:.1f}s)")
                    print(f"   Key ID: {key_id}")
                    print(f"   Name: {temp_key_name}")
                    found_keys.append((temp_key_name, key_id))
                    return temp_key_name, key_id
                
                requests.post(
                    f'{IPFS_API}/api/v0/key/rm',
                    params={'arg': temp_key_name},
                    timeout=5
                )
                
                if attempts % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = attempts / elapsed
                    print(f"Attempt #{attempts} ({rate:.0f} keys/sec)")
                    
            except requests.exceptions.RequestException as e:
                print(f"Network error: {e}")
                time.sleep(1)
                continue
    
    except KeyboardInterrupt:
        print("\n\nSearch interrupted by user.")
        if found_keys:
            print(f"\nFound {len(found_keys)} matching keys before interruption:")
            for name, kid in found_keys:
                print(f"  - {name}: {kid}")
        return None, None
    
    print(f"\nReached max attempts ({max_attempts}) without finding a match.")
    return None, None

def export_key(key_name, output_path):
    print(f"\nExporting key '{key_name}'...")
    
    try:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        temp_key_path = f'/tmp/{key_name}.key'
        
        result = subprocess.run(
            ['docker', 'compose', 'exec', 'ipfs', 'ipfs', 'key', 'export', '-o', temp_key_path, key_name],
            capture_output=True,
            cwd='/workspaces/sleet_test',
            timeout=10
        )
        
        if result.returncode != 0:
            print(f"Error exporting key: {result.stderr.decode()}")
            return None
        
        result = subprocess.run(
            ['docker', 'compose', 'cp', f'ipfs:{temp_key_path}', str(output_file)],
            capture_output=True,
            cwd='/workspaces/sleet_test',
            timeout=10
        )
        
        if result.returncode == 0:
            print(f"✓ Key exported to: {output_file}")
            return str(output_file)
        else:
            print(f"Error copying key: {result.stderr.decode()}")
            return None
            
    except Exception as e:
        print(f"Error: {e}")
        return None

def rename_key(old_name, new_name):
    print(f"\nRenaming key '{old_name}' to '{new_name}'...")
    
    try:
        response = requests.post(
            f'{IPFS_API}/api/v0/key/rename',
            params={'arg': old_name, 'arg2': new_name},
            timeout=5
        )
        
        if response.status_code == 200:
            print(f"✓ Key renamed to: {new_name}")
            return True
        else:
            print(f"Error renaming key: {response.text}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate-vanity-ipns.py <substring> [max_attempts] [final_key_name] [position]")
        print("\nExamples:")
        print("  python3 generate-vanity-ipns.py radio 50000 sleetbubble-sex")
        print("  python3 generate-vanity-ipns.py radio 50000 sleetbubble-sex end")
        print("  python3 generate-vanity-ipns.py radio 50000 sleetbubble-sex start")
        print("\nPosition options: anywhere (default), start, end")
        print("\nEstimated times (on modern CPU):")
        print("  3-4 chars: seconds to minutes")
        print("  5 chars:   30-60 minutes")
        print("  6 chars:   1-2 days")
        print("  Note: 'end' position is ~10x harder than 'anywhere'")
        sys.exit(1)
    
    substring = sys.argv[1]
    max_attempts = int(sys.argv[2]) if len(sys.argv) > 2 else 100000
    final_name = sys.argv[3] if len(sys.argv) > 3 else 'sleetbubble-sex'
    position = sys.argv[4] if len(sys.argv) > 4 else 'anywhere'
    
    print("=" * 60)
    print("IPNS Vanity Key Generator for Sleetbubble")
    print("=" * 60)
    
    try:
        response = requests.post(f'{IPFS_API}/api/v0/id', timeout=5)
        if response.status_code != 200:
            print("Error: Cannot connect to IPFS API")
            print("Make sure IPFS is running: docker compose up -d")
            sys.exit(1)
    except:
        print("Error: Cannot connect to IPFS API at", IPFS_API)
        print("Make sure IPFS is running: docker compose up -d")
        sys.exit(1)
    
    temp_name, key_id = generate_vanity_key(substring, max_attempts, position)
    
    if not temp_name:
        print("\nNo matching key found. Try:")
        print("  1. Shorter substring (4-5 chars)")
        print("  2. More max_attempts")
        print("  3. Different search term")
        sys.exit(1)
    
    export_path = f'/workspaces/sleet_test/keys/{final_name}.key'
    exported = export_key(temp_name, export_path)
    
    if exported:
        rename_key(temp_name, final_name)
        
        print("\n" + "=" * 60)
        print("SUCCESS!")
        print("=" * 60)
        print(f"IPNS Key ID: {key_id}")
        print(f"Key Name: {final_name}")
        print(f"Exported to: {export_path}")
        print("\nTo use this key on other nodes:")
        print(f"  docker compose exec ipfs ipfs key import {final_name} {export_path}")
        print(f"\nOr from the host:")
        print(f"  docker compose exec -T ipfs ipfs key import {final_name} < {export_path}")

if __name__ == '__main__':
    main()
