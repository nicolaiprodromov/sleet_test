#!/usr/bin/env python3

import os
import sys
import json
import random

def load_config(config_file):
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

def scan_music_directory(music_dir, scan_subdirectories=True):
    audio_extensions = ('.mp3', '.flac', '.wav', '.ogg', '.m4a')
    found_files = {}
    
    if scan_subdirectories:
        for root, dirs, files in os.walk(music_dir):
            for file in files:
                if file.endswith(audio_extensions):
                    full_path = os.path.join(root, file)
                    found_files[file] = full_path
    else:
        for file in os.listdir(music_dir):
            if file.endswith(audio_extensions):
                full_path = os.path.join(music_dir, file)
                if os.path.isfile(full_path):
                    found_files[file] = full_path
    
    return found_files

def build_playlist(config, music_dir, output_file):
    mode = config.get('mode', 'ordered')
    tracks = config.get('tracks', [])
    options = config.get('options', {})
    
    found_files = scan_music_directory(
        music_dir, 
        options.get('scan_subdirectories', True)
    )
    
    playlist_paths = []
    
    if mode == 'ordered':
        for track in tracks:
            if track in found_files:
                playlist_paths.append(found_files[track])
            else:
                print(f"Warning: Track not found: {track}")
        
        for filename, path in found_files.items():
            if path not in playlist_paths:
                print(f"Info: Available but not in config: {filename}")
    
    elif mode == 'auto':
        playlist_paths = list(found_files.values())
        
        if options.get('sort_alphabetically', False):
            playlist_paths.sort()
        
        if options.get('shuffle_on_build', False):
            random.shuffle(playlist_paths)
    
    elif mode == 'all':
        for track in tracks:
            if track in found_files:
                playlist_paths.append(found_files[track])
        
        for filename, path in found_files.items():
            if path not in playlist_paths:
                playlist_paths.append(path)
    
    else:
        print(f"Error: Unknown mode '{mode}'")
        sys.exit(1)
    
    with open(output_file, 'w') as f:
        for path in playlist_paths:
            f.write(f"{path}\n")
    
    print(f"Playlist generated: {output_file}")
    print(f"Total tracks: {len(playlist_paths)}")
    
    return playlist_paths

if __name__ == '__main__':
    config_file = sys.argv[1] if len(sys.argv) > 1 else '/workspace/playlist.config.json'
    music_dir = sys.argv[2] if len(sys.argv) > 2 else '/music'
    output_file = sys.argv[3] if len(sys.argv) > 3 else os.path.join(music_dir, 'playlist.m3u')
    
    print(f"Loading config: {config_file}")
    config = load_config(config_file)
    
    print(f"Scanning music directory: {music_dir}")
    build_playlist(config, music_dir, output_file)
    
    print(f"\nPlaylist built successfully!")
