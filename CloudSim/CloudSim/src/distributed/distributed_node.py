"""
Distributed storage node that runs as a separate process.
Communicates with coordinator and other nodes via TCP.
"""

import os
import sys
import time
import logging
import threading
import hashlib
from typing import Dict, Optional
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.network import NetworkServer, NetworkClient, Message, MessageType, create_message, create_success_message, create_error_message
from src.core.data_structures import FileChunk, FileMetadata, TransferStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DistributedStorageNode:
    """
    Storage node that runs as a separate process.
    Handles file storage and communicates via network.
    """
    
    def __init__(self, node_id: str, host: str, port: int, 
                 storage_capacity: int, coordinator_host: str, coordinator_port: int):
        """
        Initialize distributed storage node.
        
        Args:
            node_id: Unique node identifier
            host: Host address to bind to
            port: Port to listen on
            storage_capacity: Storage capacity in bytes
            coordinator_host: Coordinator host address
            coordinator_port: Coordinator port
        """
        self.node_id = node_id
        self.host = host
        self.port = port
        self.storage_capacity = storage_capacity
        self.coordinator_host = coordinator_host
        self.coordinator_port = coordinator_port
        
        # Storage
        self.stored_chunks: Dict[str, FileChunk] = {}
        self.stored_files: Dict[str, FileMetadata] = {}
        self.used_storage = 0
        
        # Network server
        self.server = NetworkServer(host, port, self._handle_message)
        
        # State
        self.running = False
        self.registered = False
        
        # Heartbeat
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.heartbeat_interval = 3  # seconds
        
        logger.info(f"DistributedStorageNode {node_id} initialized on {host}:{port}")
    
    def start(self):
        """Start the storage node."""
        logger.info(f"Starting node {self.node_id}...")
        
        # Start network server
        self.server.start()
        time.sleep(0.5)  # Give server time to start
        
        # Register with coordinator
        if not self._register_with_coordinator():
            logger.error("Failed to register with coordinator")
            self.stop()
            return False
        
        # Start heartbeat
        self.running = True
        self.heartbeat_thread = threading.Thread(target=self._send_heartbeats, daemon=True)
        self.heartbeat_thread.start()
        
        logger.info(f"Node {self.node_id} started successfully")
        return True
    
    def stop(self):
        """Stop the storage node."""
        logger.info(f"Stopping node {self.node_id}...")
        self.running = False
        
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=5)
        
        self.server.stop()
        logger.info(f"Node {self.node_id} stopped")
    
    def _register_with_coordinator(self) -> bool:
        """Register this node with the coordinator."""
        logger.info(f"Registering with coordinator at {self.coordinator_host}:{self.coordinator_port}")
        
        message = create_message(
            MessageType.REGISTER_NODE,
            {
                'node_id': self.node_id,
                'host': self.host,
                'port': self.port,
                'storage_capacity': self.storage_capacity
            },
            sender_id=self.node_id
        )
        
        try:
            with NetworkClient() as client:
                if not client.connect(self.coordinator_host, self.coordinator_port):
                    return False
                
                response = client.send_and_receive(message)
                if not response:
                    return False
                
                response_msg, _ = response
                if response_msg.msg_type == MessageType.NODE_REGISTERED:
                    self.registered = True
                    logger.info(f"Successfully registered with coordinator")
                    return True
                else:
                    logger.error(f"Registration failed: {response_msg.data}")
                    return False
        
        except Exception as e:
            logger.error(f"Error registering with coordinator: {e}")
            return False
    
    def _send_heartbeats(self):
        """Send periodic heartbeats to coordinator."""
        while self.running:
            try:
                message = create_message(
                    MessageType.HEARTBEAT,
                    {
                        'node_id': self.node_id,
                        'used_storage': self.used_storage,
                        'free_storage': self.storage_capacity - self.used_storage,
                        'num_chunks': len(self.stored_chunks),
                        'num_files': len(self.stored_files)
                    },
                    sender_id=self.node_id
                )
                
                with NetworkClient(timeout=5.0) as client:
                    if client.connect(self.coordinator_host, self.coordinator_port):
                        client.send_message(message)
                
            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")
            
            time.sleep(self.heartbeat_interval)
    
    def _handle_message(self, message: Message, client_socket):
        """
        Handle incoming network messages.
        
        Args:
            message: Received message
            client_socket: Client socket for sending response
        """
        logger.debug(f"Handling message: {message.msg_type.value}")
        
        try:
            if message.msg_type == MessageType.STORE_CHUNK:
                self._handle_store_chunk(message, client_socket)
            
            elif message.msg_type == MessageType.GET_CHUNK:
                self._handle_get_chunk(message, client_socket)
            
            elif message.msg_type == MessageType.GET_STATUS:
                self._handle_get_status(message, client_socket)
            
            elif message.msg_type == MessageType.REPLICATE_CHUNK:
                self._handle_replicate_chunk(message, client_socket)
            
            else:
                logger.warning(f"Unknown message type: {message.msg_type.value}")
                response = create_error_message(f"Unknown message type: {message.msg_type.value}")
                from src.network.protocol import ProtocolHandler
                ProtocolHandler.send_message(client_socket, response)
        
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            response = create_error_message(str(e))
            from src.network.protocol import ProtocolHandler
            try:
                ProtocolHandler.send_message(client_socket, response)
            except:
                pass
    
    def _handle_store_chunk(self, message: Message, client_socket):
        """Handle STORE_CHUNK message."""
        file_id = message.data['file_id']
        chunk_id = message.data['chunk_id']
        chunk_data = message.data.get('_binary_data')
        
        if not chunk_data:
            raise ValueError("No chunk data provided")
        
        # Calculate checksum
        checksum = hashlib.sha256(chunk_data).hexdigest()
        
        # Create chunk
        chunk = FileChunk(
            chunk_id=chunk_id,
            size=len(chunk_data),
            data=chunk_data,
            checksum=checksum,
            status=TransferStatus.COMPLETED
        )
        
        # Store chunk
        chunk_key = f"{file_id}_{chunk_id}"
        self.stored_chunks[chunk_key] = chunk
        self.used_storage += len(chunk_data)
        
        logger.info(f"Stored chunk {chunk_key} ({len(chunk_data)} bytes)")
        
        # Send response
        response = create_success_message({
            'file_id': file_id,
            'chunk_id': chunk_id,
            'checksum': checksum,
            'size': len(chunk_data)
        }, sender_id=self.node_id)
        
        from src.network.protocol import ProtocolHandler
        ProtocolHandler.send_message(client_socket, response)
    
    def _handle_get_chunk(self, message: Message, client_socket):
        """Handle GET_CHUNK message."""
        file_id = message.data['file_id']
        chunk_id = message.data['chunk_id']
        chunk_key = f"{file_id}_{chunk_id}"
        
        if chunk_key not in self.stored_chunks:
            raise ValueError(f"Chunk {chunk_key} not found")
        
        chunk = self.stored_chunks[chunk_key]
        
        # Send chunk data
        response = create_message(
            MessageType.CHUNK_DATA,
            {
                'file_id': file_id,
                'chunk_id': chunk_id,
                'checksum': chunk.checksum,
                'size': chunk.size
            },
            sender_id=self.node_id
        )
        
        from src.network.protocol import ProtocolHandler
        ProtocolHandler.send_message(client_socket, response, chunk.data)
        
        logger.info(f"Sent chunk {chunk_key} ({chunk.size} bytes)")
    
    def _handle_get_status(self, message: Message, client_socket):
        """Handle GET_STATUS message."""
        response = create_message(
            MessageType.STATUS_RESPONSE,
            {
                'node_id': self.node_id,
                'storage_capacity': self.storage_capacity,
                'used_storage': self.used_storage,
                'free_storage': self.storage_capacity - self.used_storage,
                'num_chunks': len(self.stored_chunks),
                'num_files': len(self.stored_files),
                'running': self.running
            },
            sender_id=self.node_id
        )
        
        from src.network.protocol import ProtocolHandler
        ProtocolHandler.send_message(client_socket, response)
    
    def _handle_replicate_chunk(self, message: Message, client_socket):
        """Handle REPLICATE_CHUNK message (copy chunk from another node)."""
        # This would fetch chunk from another node and store it
        # For now, just acknowledge
        response = create_success_message(sender_id=self.node_id)
        from src.network.protocol import ProtocolHandler
        ProtocolHandler.send_message(client_socket, response)
    
    def run_forever(self):
        """Run the node forever (blocking)."""
        try:
            logger.info(f"Node {self.node_id} running. Press Ctrl+C to stop.")
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            self.stop()

