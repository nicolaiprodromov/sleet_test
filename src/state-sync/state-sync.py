#!/usr/bin/env python3

import os
import sys
import json
import requests
import time
import threading
import base64
from datetime import datetime

IPFS_API = os.getenv('IPFS_API', 'http://ipfs:5001')
NODE_ID = os.getenv('NODE_ID', 'unknown')
STREAM_TOPIC = os.getenv('STREAM_TOPIC', 'sleetbubble-stream')
STATE_DIR = '/state'

def encode_topic_multibase(topic):
    encoded = base64.urlsafe_b64encode(topic.encode()).decode().rstrip('=')
    return 'u' + encoded

class StateSync:
    def __init__(self):
        self.state_file = os.path.join(STATE_DIR, 'current_position.json')
        self.remote_states = {}
        self.local_state = None
        self.running = True
        
        os.makedirs(STATE_DIR, exist_ok=True)
        
    def wait_for_ipfs(self):
        print("Waiting for IPFS to be ready...")
        while self.running:
            try:
                response = requests.post(f'{IPFS_API}/api/v0/id', timeout=2)
                if response.status_code == 200:
                    print("IPFS is ready")
                    return True
            except:
                pass
            time.sleep(2)
        return False
    
    def subscribe_to_topic(self):
        print(f"Subscribing to topic: {STREAM_TOPIC}")
        encoded_topic = encode_topic_multibase(STREAM_TOPIC)
        print(f"Encoded topic (multibase): {encoded_topic}")
        
        try:
            response = requests.post(
                f'{IPFS_API}/api/v0/pubsub/sub',
                params={'arg': encoded_topic},
                stream=True,
                timeout=None
            )
            
            if response.status_code != 200:
                print(f"Failed to subscribe: HTTP {response.status_code}")
                print(f"Response: {response.text}")
                raise Exception(f"Subscription failed with status {response.status_code}")
            
            print(f"Successfully subscribed, waiting for messages...")
            
            for line in response.iter_lines(chunk_size=1, decode_unicode=False):
                if not self.running:
                    break
                    
                if line:
                    try:
                        message = json.loads(line.decode('utf-8'))
                        if 'data' in message:
                            data_multibase = message['data']
                            if data_multibase.startswith('u'):
                                data_base64 = data_multibase[1:]
                                data_bytes = base64.urlsafe_b64decode(data_base64 + '==')
                                data = json.loads(data_bytes.decode('utf-8'))
                                self.handle_state_update(data)
                            else:
                                print(f"Unexpected encoding prefix: {data_multibase[0]}")
                    except json.JSONDecodeError as e:
                        print(f"JSON decode error: {e}")
                    except Exception as e:
                        print(f"Error parsing message: {e}")
                        
        except Exception as e:
            print(f"Error subscribing to topic: {e}")
            if self.running:
                time.sleep(5)
                self.subscribe_to_topic()
    
    def handle_state_update(self, state):
        node_id = state.get('node_id', 'unknown')
        timestamp = state.get('timestamp', 0)
        
        print(f"Received state from {node_id}: position={state.get('position')}, track={state.get('track')}")
        
        self.remote_states[node_id] = {
            'state': state,
            'timestamp': timestamp,
            'received_at': time.time()
        }
        
        self.sync_state()
    
    def sync_state(self):
        if not self.remote_states:
            return
        
        latest_state = None
        latest_timestamp = 0
        
        for node_id, data in self.remote_states.items():
            if data['timestamp'] > latest_timestamp:
                latest_timestamp = data['timestamp']
                latest_state = data['state']
        
        if latest_state:
            current_time = time.time()
            age = current_time - latest_timestamp
            
            if age < 300:
                with open(self.state_file, 'w') as f:
                    json.dump(latest_state, f, indent=2)
                
                self.local_state = latest_state
                print(f"Synced to state from {latest_state.get('node_id')}")
    
    def cleanup_old_states(self):
        while self.running:
            time.sleep(60)
            current_time = time.time()
            
            for node_id in list(self.remote_states.keys()):
                age = current_time - self.remote_states[node_id]['received_at']
                if age > 600:
                    print(f"Removing stale state from {node_id}")
                    del self.remote_states[node_id]
    
    def publish_local_state(self):
        while self.running:
            try:
                if os.path.exists(self.state_file):
                    with open(self.state_file, 'r') as f:
                        state = json.load(f)
                    
                    if state != self.local_state:
                        encoded_topic = encode_topic_multibase(STREAM_TOPIC)
                        data = {
                            'arg': encoded_topic
                        }
                        files = {
                            'data': json.dumps(state)
                        }
                        
                        response = requests.post(
                            f'{IPFS_API}/api/v0/pubsub/pub',
                            params=data,
                            files=files,
                            timeout=5
                        )
                        
                        if response.status_code == 200:
                            self.local_state = state
                            print(f"Published local state: position={state.get('position')}")
                        else:
                            print(f"Failed to publish: HTTP {response.status_code}")
                        
            except Exception as e:
                print(f"Error publishing state: {e}")
            
            time.sleep(10)
    
    def run(self):
        if not self.wait_for_ipfs():
            return
        
        pub_thread = threading.Thread(target=self.publish_local_state)
        pub_thread.daemon = True
        pub_thread.start()
        
        cleanup_thread = threading.Thread(target=self.cleanup_old_states)
        cleanup_thread.daemon = True
        cleanup_thread.start()
        
        try:
            self.subscribe_to_topic()
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.running = False

if __name__ == '__main__':
    sync = StateSync()
    sync.run()
