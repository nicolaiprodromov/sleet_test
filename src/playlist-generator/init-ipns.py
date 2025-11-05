#!/usr/bin/env python3
"""
IPNS Initialization Script
Sets up IPNS keys for the P2P radio streaming system.
Run this once before starting the streaming services.
"""

import os
import sys
import json
import requests
import logging

# Configuration
IPFS_API = os.getenv('IPFS_API', 'http://localhost:5001')
STATE_DIR = os.getenv('STATE_DIR', './data/state')
NODE_ID = os.getenv('NODE_ID', 'node1')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_ipfs_connection():
    """Check if IPFS daemon is running"""
    try:
        response = requests.post(f'{IPFS_API}/api/v0/id', timeout=5)
        if response.status_code == 200:
            ipfs_info = response.json()
            logger.info(f"✓ Connected to IPFS node")
            logger.info(f"  Node ID: {ipfs_info['ID']}")
            logger.info(f"  Agent: {ipfs_info.get('AgentVersion', 'Unknown')}")
            return True
        else:
            logger.error("IPFS API returned error")
            return False
    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to IPFS daemon")
        logger.error(f"Make sure IPFS is running and accessible at {IPFS_API}")
        return False
    except Exception as e:
        logger.error(f"Error checking IPFS: {e}")
        return False


def create_ipns_key(name, key_type='ed25519'):
    """Create an IPNS key"""
    try:
        # Check if key already exists
        response = requests.post(f'{IPFS_API}/api/v0/key/list', timeout=5)
        if response.status_code == 200:
            existing_keys = response.json().get('Keys', [])
            for key in existing_keys:
                if key['Name'] == name:
                    logger.info(f"✓ Key '{name}' already exists: {key['Id']}")
                    return key['Id']
        
        # Create new key
        logger.info(f"Creating IPNS key: {name}")
        response = requests.post(
            f'{IPFS_API}/api/v0/key/gen',
            params={'arg': name, 'type': key_type},
            timeout=10
        )
        
        if response.status_code == 200:
            key_info = response.json()
            key_id = key_info['Id']
            logger.info(f"✓ Created key '{name}': {key_id}")
            return key_id
        else:
            logger.error(f"Failed to create key '{name}': {response.text}")
            return None
    
    except Exception as e:
        logger.error(f"Error creating key '{name}': {e}")
        return None


def save_ipns_state(keys):
    """Save IPNS keys to state file"""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        state_file = os.path.join(STATE_DIR, 'ipns_keys.json')
        
        with open(state_file, 'w') as f:
            json.dump(keys, f, indent=2)
        
        logger.info(f"✓ Saved IPNS state to {state_file}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to save IPNS state: {e}")
        return False


def initialize_ipns_keys():
    """Initialize all IPNS keys for the streaming system"""
    logger.info("=" * 60)
    logger.info("IPNS Initialization for P2P Radio")
    logger.info("=" * 60)
    
    # Check IPFS connection
    if not check_ipfs_connection():
        logger.error("Cannot proceed without IPFS connection")
        return False
    
    logger.info("")
    logger.info(f"Node ID: {NODE_ID}")
    logger.info("Creating IPNS keys for streaming...")
    logger.info("")
    
    keys = {}
    
    # Create master playlist key
    master_key_name = f'{NODE_ID}-master'
    master_key_id = create_ipns_key(master_key_name)
    if master_key_id:
        keys[master_key_name] = master_key_id
    else:
        logger.error("Failed to create master key!")
        return False
    
    key_name = f'{NODE_ID}-stream'
    key_id = create_ipns_key(key_name)
    if key_id:
        keys[key_name] = key_id
    else:
        logger.error("Failed to create stream key!")
        return False
    
    # Save state
    if not save_ipns_state(keys):
        return False
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✓ IPNS Initialization Complete!")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Stream URLs (use these to access your radio):")
    logger.info(f"  Master Playlist: /ipns/{keys[f'{NODE_ID}-master']}")
    logger.info(f"  Stream Playlist: /ipns/{keys[f'{NODE_ID}-stream']}")
    logger.info("")
    logger.info("These IPNS names are permanent and mutable.")
    logger.info("The content they point to will update automatically.")
    logger.info("")
    
    return True


def main():
    if not initialize_ipns_keys():
        logger.error("Initialization failed!")
        sys.exit(1)
    
    logger.info("You can now start the streaming services.")


if __name__ == '__main__':
    main()
