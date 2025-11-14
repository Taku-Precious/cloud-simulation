#!/usr/bin/env python3
"""
Script to start the distributed coordinator.

Usage:
    python start_coordinator.py [--host HOST] [--port PORT]

Example:
    python start_coordinator.py --host localhost --port 5000
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.distributed import DistributedCoordinator


def main():
    parser = argparse.ArgumentParser(description='Start CloudSim Distributed Coordinator')
    parser.add_argument('--host', default='localhost', help='Host address to bind to (default: localhost)')
    parser.add_argument('--port', type=int, default=5000, help='Port to listen on (default: 5000)')
    
    args = parser.parse_args()
    
    print("="*70)
    print("  CloudSim Distributed Coordinator")
    print("="*70)
    print(f"  Host: {args.host}")
    print(f"  Port: {args.port}")
    print("="*70)
    print()
    
    # Create and start coordinator
    coordinator = DistributedCoordinator(args.host, args.port)
    coordinator.start()
    
    # Run forever
    coordinator.run_forever()


if __name__ == '__main__':
    main()

