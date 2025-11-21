#!/usr/bin/env python3
"""
Script to start a distributed storage node.

Usage:
    python start_node.py NODE_ID [--host HOST] [--port PORT] [--storage STORAGE_GB] [--coordinator-host HOST] [--coordinator-port PORT]

Example:
    python start_node.py node-1 --port 6001 --storage 100
    python start_node.py node-2 --port 6002 --storage 150
    python start_node.py node-3 --port 6003 --storage 200
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.distributed import DistributedStorageNode


def main():
    parser = argparse.ArgumentParser(description='Start CloudSim Distributed Storage Node')
    parser.add_argument('node_id', help='Unique node identifier (e.g., node-1, node-2)')
    parser.add_argument('--host', default='localhost', help='Host address to bind to (default: localhost)')
    parser.add_argument('--port', type=int, required=True, help='Port to listen on (required)')
    parser.add_argument('--storage', type=int, default=100, help='Storage capacity in GB (default: 100)')
    parser.add_argument('--coordinator-host', default='localhost', help='Coordinator host (default: localhost)')
    parser.add_argument('--coordinator-port', type=int, default=5000, help='Coordinator port (default: 5000)')
    
    args = parser.parse_args()
    
    # Convert storage from GB to bytes
    storage_bytes = args.storage * 1024 * 1024 * 1024
    
    print("="*70)
    print(f"  CloudSim Distributed Storage Node: {args.node_id}")
    print("="*70)
    print(f"  Node ID: {args.node_id}")
    print(f"  Host: {args.host}")
    print(f"  Port: {args.port}")
    print(f"  Storage: {args.storage} GB")
    print(f"  Coordinator: {args.coordinator_host}:{args.coordinator_port}")
    print("="*70)
    print()
    
    # Create and start node
    node = DistributedStorageNode(
        node_id=args.node_id,
        host=args.host,
        port=args.port,
        storage_capacity=storage_bytes,
        coordinator_host=args.coordinator_host,
        coordinator_port=args.coordinator_port
    )
    
    if node.start():
        # Run forever
        node.run_forever()
    else:
        print("Failed to start node")
        sys.exit(1)


if __name__ == '__main__':
    main()

