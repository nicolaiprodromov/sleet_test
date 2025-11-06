#!/usr/bin/env python3

import os
import sys
import json
import shutil
from pathlib import Path

def resolve_source_path(source_path, config_dir):
    path = Path(source_path)
    
    if path.is_absolute():
        return path
    
    return (Path(config_dir) / path).resolve()

def copy_music_files(config_path, destination_dir):
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    source_path = config.get('source', '')
    
    if not source_path:
        print("No source path specified in config. Skipping music copy.")
        return 0
    
    config_dir = Path(config_path).parent
    resolved_source = resolve_source_path(source_path, config_dir)
    
    if not resolved_source.exists():
        print(f"ERROR: Source path does not exist: {resolved_source}")
        sys.exit(1)
    
    if not resolved_source.is_dir():
        print(f"ERROR: Source path is not a directory: {resolved_source}")
        sys.exit(1)
    
    os.makedirs(destination_dir, exist_ok=True)
    
    tracks = config.get('tracks', [])
    options = config.get('options', {})
    scan_subdirs = options.get('scan_subdirectories', True)
    
    copied_count = 0
    
    if tracks:
        print(f"Copying {len(tracks)} specified tracks from {resolved_source} to {destination_dir}...")
        
        for track in tracks:
            source_file = resolved_source / track
            
            if not source_file.exists():
                if scan_subdirs:
                    found_files = list(resolved_source.rglob(track))
                    if found_files:
                        source_file = found_files[0]
                    else:
                        print(f"WARNING: Track not found: {track}")
                        continue
                else:
                    print(f"WARNING: Track not found: {track}")
                    continue
            
            dest_file = Path(destination_dir) / source_file.name
            
            if dest_file.exists():
                print(f"  Skipping (already exists): {source_file.name}")
                continue
            
            try:
                shutil.copy2(source_file, dest_file)
                print(f"  Copied: {source_file.name}")
                copied_count += 1
            except Exception as e:
                print(f"  ERROR copying {source_file.name}: {e}")
    
    else:
        print(f"No tracks specified. Copying all audio files from {resolved_source}...")
        
        audio_extensions = ['.mp3', '.flac', '.wav', '.ogg', '.m4a']
        
        if scan_subdirs:
            for ext in audio_extensions:
                for source_file in resolved_source.rglob(f'*{ext}'):
                    dest_file = Path(destination_dir) / source_file.name
                    
                    if dest_file.exists():
                        print(f"  Skipping (already exists): {source_file.name}")
                        continue
                    
                    try:
                        shutil.copy2(source_file, dest_file)
                        print(f"  Copied: {source_file.name}")
                        copied_count += 1
                    except Exception as e:
                        print(f"  ERROR copying {source_file.name}: {e}")
        else:
            for source_file in resolved_source.iterdir():
                if source_file.is_file() and source_file.suffix.lower() in audio_extensions:
                    dest_file = Path(destination_dir) / source_file.name
                    
                    if dest_file.exists():
                        print(f"  Skipping (already exists): {source_file.name}")
                        continue
                    
                    try:
                        shutil.copy2(source_file, dest_file)
                        print(f"  Copied: {source_file.name}")
                        copied_count += 1
                    except Exception as e:
                        print(f"  ERROR copying {source_file.name}: {e}")
    
    print(f"\n✓ Copied {copied_count} music files to {destination_dir}")
    return copied_count

if __name__ == '__main__':
    config_path = sys.argv[1] if len(sys.argv) > 1 else '/workspace/playlist.config.json'
    destination_dir = sys.argv[2] if len(sys.argv) > 2 else '/music'
    
    print("=================================")
    print("Music Copy Service")
    print("=================================")
    print(f"Config: {config_path}")
    print(f"Destination: {destination_dir}")
    print("")
    
    copy_music_files(config_path, destination_dir)
