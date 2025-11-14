"""
Distributed coordinator that manages storage nodes.
Runs as a separate process and coordinates file storage across nodes.
"""

import sys
import time
import logging
import threading
from typing import Dict, List, Optional, Set
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.network import NetworkServer, NetworkClient, Message, MessageType, create_message, create_success_message, create_error_message

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class NodeInfo:
    """Information about a registered storage node."""
    node_id: str
    host: str
    port: int
    storage_capacity: int
    used_storage: int = 0
    last_heartbeat: float = 0.0
    status: str = "HEALTHY"  # HEALTHY, FAILED, OFFLINE


class DistributedCoordinator:
    """
    Coordinator that manages distributed storage nodes.
    Handles node registration, file distribution, and failure detection.
    """
    
    def __init__(self, host: str, port: int):
        """
        Initialize distributed coordinator.
        
        Args:
            host: Host address to bind to
            port: Port to listen on
        """
        self.host = host
        self.port = port
        
        # Registered nodes
        self.nodes: Dict[str, NodeInfo] = {}
        self.nodes_lock = threading.Lock()
        
        # File to nodes mapping
        self.file_locations: Dict[str, Set[str]] = {}  # file_id -> set of node_ids
        self.file_locations_lock = threading.Lock()
        
        # Network server
        self.server = NetworkServer(host, port, self._handle_message)
        
        # State
        self.running = False
        
        # Heartbeat monitoring
        self.monitor_thread: Optional[threading.Thread] = None
        self.heartbeat_timeout = 30  # seconds
        
        logger.info(f"DistributedCoordinator initialized on {host}:{port}")
    
    def start(self):
        """Start the coordinator."""
        logger.info("Starting coordinator...")
        
        # Start network server
        self.server.start()
        
        # Start heartbeat monitor
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_heartbeats, daemon=True)
        self.monitor_thread.start()
        
        logger.info(f"Coordinator started on {self.host}:{self.port}")
    
    def stop(self):
        """Stop the coordinator."""
        logger.info("Stopping coordinator...")
        self.running = False
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        self.server.stop()
        logger.info("Coordinator stopped")
    
    def _handle_message(self, message: Message, client_socket):
        """
        Handle incoming network messages.
        
        Args:
            message: Received message
            client_socket: Client socket for sending response
        """
        logger.debug(f"Handling message: {message.msg_type.value}")
        
        try:
            if message.msg_type == MessageType.REGISTER_NODE:
                self._handle_register_node(message, client_socket)
            
            elif message.msg_type == MessageType.HEARTBEAT:
                self._handle_heartbeat(message, client_socket)
            
            elif message.msg_type == MessageType.UPLOAD_FILE:
                self._handle_upload_file(message, client_socket)
            
            elif message.msg_type == MessageType.DOWNLOAD_FILE:
                self._handle_download_file(message, client_socket)
            
            elif message.msg_type == MessageType.DISCOVER_NODES:
                self._handle_discover_nodes(message, client_socket)
            
            elif message.msg_type == MessageType.GET_STATUS:
                self._handle_get_status(message, client_socket)
            
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
    
    def _handle_register_node(self, message: Message, client_socket):
        """Handle node registration."""
        node_id = message.data['node_id']
        host = message.data['host']
        port = message.data['port']
        storage_capacity = message.data['storage_capacity']
        
        with self.nodes_lock:
            self.nodes[node_id] = NodeInfo(
                node_id=node_id,
                host=host,
                port=port,
                storage_capacity=storage_capacity,
                last_heartbeat=time.time(),
                status="HEALTHY"
            )
        
        logger.info(f"Registered node {node_id} at {host}:{port} ({storage_capacity} bytes)")
        
        # Send response
        response = create_message(
            MessageType.NODE_REGISTERED,
            {
                'node_id': node_id,
                'status': 'registered'
            }
        )
        
        from src.network.protocol import ProtocolHandler
        ProtocolHandler.send_message(client_socket, response)
    
    def _handle_heartbeat(self, message: Message, client_socket):
        """Handle heartbeat from node."""
        node_id = message.data['node_id']
        
        with self.nodes_lock:
            if node_id in self.nodes:
                node = self.nodes[node_id]
                node.last_heartbeat = time.time()
                node.used_storage = message.data.get('used_storage', 0)
                
                # If node was failed, mark as recovered
                if node.status == "FAILED":
                    node.status = "HEALTHY"
                    logger.info(f"Node {node_id} recovered")
        
        # Send ACK
        response = create_message(MessageType.HEARTBEAT_ACK, {})
        from src.network.protocol import ProtocolHandler
        try:
            ProtocolHandler.send_message(client_socket, response)
        except:
            pass  # Heartbeat ACK is optional
    
    def _handle_upload_file(self, message: Message, client_socket):
        """Handle file upload request."""
        file_id = message.data['file_id']
        file_size = message.data['file_size']
        replication_factor = message.data.get('replication_factor', 3)
        
        # Select nodes for storage
        selected_nodes = self._select_nodes_for_file(file_size, replication_factor)
        
        if len(selected_nodes) < replication_factor:
            raise ValueError(f"Not enough nodes available (need {replication_factor}, have {len(selected_nodes)})")
        
        # Store file location mapping
        with self.file_locations_lock:
            self.file_locations[file_id] = set(selected_nodes)
        
        logger.info(f"File {file_id} will be stored on nodes: {selected_nodes}")
        
        # Send response with node list
        response = create_message(
            MessageType.UPLOAD_ACK,
            {
                'file_id': file_id,
                'nodes': [
                    {
                        'node_id': node_id,
                        'host': self.nodes[node_id].host,
                        'port': self.nodes[node_id].port
                    }
                    for node_id in selected_nodes
                ]
            }
        )
        
        from src.network.protocol import ProtocolHandler
        ProtocolHandler.send_message(client_socket, response)
    
    def _handle_download_file(self, message: Message, client_socket):
        """Handle file download request."""
        file_id = message.data['file_id']
        
        with self.file_locations_lock:
            if file_id not in self.file_locations:
                raise ValueError(f"File {file_id} not found")
            
            node_ids = list(self.file_locations[file_id])
        
        # Filter for healthy nodes
        with self.nodes_lock:
            healthy_nodes = [
                node_id for node_id in node_ids
                if node_id in self.nodes and self.nodes[node_id].status == "HEALTHY"
            ]
        
        if not healthy_nodes:
            raise ValueError(f"No healthy nodes have file {file_id}")
        
        # Return first healthy node
        node_id = healthy_nodes[0]
        node = self.nodes[node_id]
        
        response = create_message(
            MessageType.FILE_DATA,
            {
                'file_id': file_id,
                'node': {
                    'node_id': node_id,
                    'host': node.host,
                    'port': node.port
                }
            }
        )
        
        from src.network.protocol import ProtocolHandler
        ProtocolHandler.send_message(client_socket, response)
    
    def _handle_discover_nodes(self, message: Message, client_socket):
        """Handle node discovery request."""
        with self.nodes_lock:
            nodes_list = [
                {
                    'node_id': node.node_id,
                    'host': node.host,
                    'port': node.port,
                    'storage_capacity': node.storage_capacity,
                    'used_storage': node.used_storage,
                    'status': node.status
                }
                for node in self.nodes.values()
            ]
        
        response = create_message(
            MessageType.NODES_LIST,
            {'nodes': nodes_list}
        )
        
        from src.network.protocol import ProtocolHandler
        ProtocolHandler.send_message(client_socket, response)
    
    def _handle_get_status(self, message: Message, client_socket):
        """Handle status request."""
        with self.nodes_lock:
            total_nodes = len(self.nodes)
            healthy_nodes = sum(1 for n in self.nodes.values() if n.status == "HEALTHY")
            failed_nodes = sum(1 for n in self.nodes.values() if n.status == "FAILED")
            total_storage = sum(n.storage_capacity for n in self.nodes.values())
            used_storage = sum(n.used_storage for n in self.nodes.values())
        
        with self.file_locations_lock:
            total_files = len(self.file_locations)
        
        response = create_message(
            MessageType.STATUS_RESPONSE,
            {
                'total_nodes': total_nodes,
                'healthy_nodes': healthy_nodes,
                'failed_nodes': failed_nodes,
                'total_storage': total_storage,
                'used_storage': used_storage,
                'total_files': total_files
            }
        )
        
        from src.network.protocol import ProtocolHandler
        ProtocolHandler.send_message(client_socket, response)
    
    def _select_nodes_for_file(self, file_size: int, replication_factor: int) -> List[str]:
        """Select nodes for storing a file."""
        with self.nodes_lock:
            # Filter healthy nodes with enough space
            suitable_nodes = [
                (node_id, node)
                for node_id, node in self.nodes.items()
                if node.status == "HEALTHY" and 
                   (node.storage_capacity - node.used_storage) >= file_size
            ]
            
            # Sort by free space (descending)
            suitable_nodes.sort(key=lambda x: x[1].storage_capacity - x[1].used_storage, reverse=True)
            
            # Select top N nodes
            selected = [node_id for node_id, _ in suitable_nodes[:replication_factor]]
            
            return selected
    
    def _monitor_heartbeats(self):
        """Monitor node heartbeats and detect failures."""
        while self.running:
            current_time = time.time()
            
            with self.nodes_lock:
                for node_id, node in self.nodes.items():
                    time_since_heartbeat = current_time - node.last_heartbeat
                    
                    if time_since_heartbeat > self.heartbeat_timeout:
                        if node.status == "HEALTHY":
                            node.status = "FAILED"
                            logger.warning(f"Node {node_id} failed (no heartbeat for {time_since_heartbeat:.1f}s)")
            
            time.sleep(5)  # Check every 5 seconds
    
    def run_forever(self):
        """Run the coordinator forever (blocking)."""
        try:
            logger.info("Coordinator running. Press Ctrl+C to stop.")
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            self.stop()
    
    def print_status(self):
        """Print current system status."""
        with self.nodes_lock:
            print("\n" + "="*60)
            print("COORDINATOR STATUS")
            print("="*60)
            print(f"Total Nodes: {len(self.nodes)}")
            print(f"Healthy Nodes: {sum(1 for n in self.nodes.values() if n.status == 'HEALTHY')}")
            print(f"Failed Nodes: {sum(1 for n in self.nodes.values() if n.status == 'FAILED')}")
            print("\nRegistered Nodes:")
            for node in self.nodes.values():
                free_space = node.storage_capacity - node.used_storage
                print(f"  - {node.node_id}: {node.status} | {node.host}:{node.port} | "
                      f"Free: {free_space/(1024**3):.2f}GB")
            print("="*60 + "\n")

