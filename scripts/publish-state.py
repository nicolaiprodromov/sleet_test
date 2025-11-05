#!/usr/bin/env python3

import os
import sys
import json
import requests

IPFS_API = os.getenv('IPFS_API', 'http://ipfs:5001')
STREAM_TOPIC = os.getenv('STREAM_TOPIC', 'p2p-radio-stream')

def publish_state(state_file):
    try:
        with open(state_file, 'r') as f:
            state_data = f.read()
        
        data = {
            'arg': STREAM_TOPIC
        }
        files = {
            'data': state_data
        }
        
        response = requests.post(
            f'{IPFS_API}/api/v0/pubsub/pub',
            params=data,
            files=files
        )
        
        if response.status_code == 200:
            print(f"Published state to topic: {STREAM_TOPIC}")
        else:
            print(f"Error publishing state: {response.text}")
            
    except Exception as e:
        print(f"Exception publishing state: {e}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: publish-state.py <state_file>")
        sys.exit(1)
    
    state_file = sys.argv[1]
    publish_state(state_file)
