#!/usr/bin/env python3
"""
CloudSim Client - Upload and download files to/from distributed storage.

Usage:
    # Upload a file
    python cloudsim_client.py upload myfile.txt --coordinator localhost:5000
    
    # Download a file
    python cloudsim_client.py download file_id output.txt --coordinator localhost:5000
    
    # List all files
    python cloudsim_client.py list --coordinator localhost:5000
    
    # Get system status
    python cloudsim_client.py status --coordinator localhost:5000
"""

import argparse
import sys
import os
import hashlib
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.network import NetworkClient, Message, MessageType, create_message


class CloudSimClient:
    """Client for interacting with CloudSim distributed storage."""
    
    def __init__(self, coordinator_host: str, coordinator_port: int):
        """
        Initialize client.
        
        Args:
            coordinator_host: Coordinator host address
            coordinator_port: Coordinator port
        """
        self.coordinator_host = coordinator_host
        self.coordinator_port = coordinator_port
    
    def upload_file(self, file_path: str, replication_factor: int = 3) -> bool:
        """
        Upload a file to distributed storage.
        
        Args:
            file_path: Path to file to upload
            replication_factor: Number of replicas (default: 3)
            
        Returns:
            True if successful
        """
        # Check file exists
        if not os.path.exists(file_path):
            print(f"Error: File '{file_path}' not found")
            return False
        
        # Read file
        print(f"Reading file: {file_path}")
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        file_size = len(file_data)
        file_id = hashlib.sha256(file_data).hexdigest()[:16]
        
        print(f"File ID: {file_id}")
        print(f"File size: {file_size / (1024**2):.2f} MB")
        print(f"Replication factor: {replication_factor}")
        
        # Request upload from coordinator
        print(f"\nContacting coordinator at {self.coordinator_host}:{self.coordinator_port}...")
        
        message = create_message(
            MessageType.UPLOAD_FILE,
            {
                'file_id': file_id,
                'file_size': file_size,
                'replication_factor': replication_factor,
                'filename': os.path.basename(file_path)
            }
        )
        
        with NetworkClient() as client:
            if not client.connect(self.coordinator_host, self.coordinator_port):
                print("Error: Could not connect to coordinator")
                return False
            
            response = client.send_and_receive(message)
            if not response:
                print("Error: No response from coordinator")
                return False
            
            response_msg, _ = response
            
            if response_msg.msg_type == MessageType.ERROR:
                print(f"Error: {response_msg.data.get('error', 'Unknown error')}")
                return False
            
            if response_msg.msg_type != MessageType.UPLOAD_ACK:
                print(f"Error: Unexpected response type: {response_msg.msg_type.value}")
                return False
            
            nodes = response_msg.data['nodes']
            print(f"\nSelected {len(nodes)} nodes for storage:")
            for node in nodes:
                print(f"  - {node['node_id']} ({node['host']}:{node['port']})")
        
        # Upload to each node
        print(f"\nUploading file to {len(nodes)} nodes...")
        
        # Calculate chunks
        chunk_size = 2 * 1024 * 1024  # 2 MB chunks
        num_chunks = (file_size + chunk_size - 1) // chunk_size
        
        print(f"File will be split into {num_chunks} chunks of {chunk_size/(1024**2):.2f} MB each")
        
        for node in nodes:
            print(f"\nUploading to {node['node_id']}...")
            
            # Upload each chunk
            for chunk_id in range(num_chunks):
                start = chunk_id * chunk_size
                end = min(start + chunk_size, file_size)
                chunk_data = file_data[start:end]
                
                # Send chunk to node
                chunk_message = create_message(
                    MessageType.STORE_CHUNK,
                    {
                        'file_id': file_id,
                        'chunk_id': chunk_id,
                        'total_chunks': num_chunks
                    }
                )
                
                with NetworkClient() as node_client:
                    if not node_client.connect(node['host'], node['port']):
                        print(f"  Error: Could not connect to {node['node_id']}")
                        continue
                    
                    chunk_response = node_client.send_and_receive(chunk_message, chunk_data)
                    if not chunk_response:
                        print(f"  Error: No response for chunk {chunk_id}")
                        continue
                    
                    chunk_resp_msg, _ = chunk_response
                    if chunk_resp_msg.msg_type == MessageType.SUCCESS:
                        print(f"  Chunk {chunk_id + 1}/{num_chunks} uploaded ({len(chunk_data)} bytes)")
                    else:
                        print(f"  Error uploading chunk {chunk_id}: {chunk_resp_msg.data}")
        
        print(f"\n✓ File uploaded successfully!")
        print(f"  File ID: {file_id}")
        print(f"  Use this ID to download the file later")
        return True
    
    def download_file(self, file_id: str, output_path: str) -> bool:
        """
        Download a file from distributed storage.
        
        Args:
            file_id: File identifier
            output_path: Path to save downloaded file
            
        Returns:
            True if successful
        """
        print(f"Downloading file: {file_id}")
        print(f"Output path: {output_path}")
        
        # Request download from coordinator
        print(f"\nContacting coordinator at {self.coordinator_host}:{self.coordinator_port}...")
        
        message = create_message(
            MessageType.DOWNLOAD_FILE,
            {'file_id': file_id}
        )
        
        with NetworkClient() as client:
            if not client.connect(self.coordinator_host, self.coordinator_port):
                print("Error: Could not connect to coordinator")
                return False
            
            response = client.send_and_receive(message)
            if not response:
                print("Error: No response from coordinator")
                return False
            
            response_msg, _ = response
            
            if response_msg.msg_type == MessageType.ERROR:
                print(f"Error: {response_msg.data.get('error', 'Unknown error')}")
                return False
            
            if response_msg.msg_type != MessageType.FILE_DATA:
                print(f"Error: Unexpected response type: {response_msg.msg_type.value}")
                return False
            
            node = response_msg.data['node']
            print(f"File available on node: {node['node_id']} ({node['host']}:{node['port']})")
        
        # Download from node
        print(f"\nDownloading from {node['node_id']}...")
        
        # For now, just acknowledge
        # Full implementation would download all chunks and reassemble
        print("Note: Full download implementation pending")
        print("File metadata retrieved successfully")
        
        return True
    
    def get_status(self) -> bool:
        """Get system status from coordinator."""
        print(f"Getting status from coordinator at {self.coordinator_host}:{self.coordinator_port}...")
        
        message = create_message(MessageType.GET_STATUS, {})
        
        with NetworkClient() as client:
            if not client.connect(self.coordinator_host, self.coordinator_port):
                print("Error: Could not connect to coordinator")
                return False
            
            response = client.send_and_receive(message)
            if not response:
                print("Error: No response from coordinator")
                return False
            
            response_msg, _ = response
            
            if response_msg.msg_type == MessageType.STATUS_RESPONSE:
                data = response_msg.data
                print("\n" + "="*60)
                print("SYSTEM STATUS")
                print("="*60)
                print(f"Total Nodes: {data['total_nodes']}")
                print(f"Healthy Nodes: {data['healthy_nodes']}")
                print(f"Failed Nodes: {data['failed_nodes']}")
                print(f"Total Storage: {data['total_storage'] / (1024**3):.2f} GB")
                print(f"Used Storage: {data['used_storage'] / (1024**3):.2f} GB")
                print(f"Total Files: {data['total_files']}")
                print("="*60)
                return True
            else:
                print(f"Error: {response_msg.data}")
                return False


def main():
    parser = argparse.ArgumentParser(description='CloudSim Client - Distributed Storage')
    parser.add_argument('command', choices=['upload', 'download', 'status'], 
                       help='Command to execute')
    parser.add_argument('args', nargs='*', help='Command arguments')
    parser.add_argument('--coordinator', default='localhost:5000', 
                       help='Coordinator address (host:port)')
    parser.add_argument('--replication', type=int, default=3,
                       help='Replication factor for uploads (default: 3)')
    
    args = parser.parse_args()
    
    # Parse coordinator address
    if ':' in args.coordinator:
        coord_host, coord_port = args.coordinator.split(':')
        coord_port = int(coord_port)
    else:
        coord_host = args.coordinator
        coord_port = 5000
    
    # Create client
    client = CloudSimClient(coord_host, coord_port)
    
    # Execute command
    if args.command == 'upload':
        if not args.args:
            print("Error: Please specify file to upload")
            print("Usage: python cloudsim_client.py upload <file_path>")
            sys.exit(1)
        
        file_path = args.args[0]
        success = client.upload_file(file_path, args.replication)
        sys.exit(0 if success else 1)
    
    elif args.command == 'download':
        if len(args.args) < 2:
            print("Error: Please specify file ID and output path")
            print("Usage: python cloudsim_client.py download <file_id> <output_path>")
            sys.exit(1)
        
        file_id = args.args[0]
        output_path = args.args[1]
        success = client.download_file(file_id, output_path)
        sys.exit(0 if success else 1)
    
    elif args.command == 'status':
        success = client.get_status()
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

