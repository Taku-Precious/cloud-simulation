"""
Storage Virtual Network - Enhanced Version
Production-grade network coordinator with replication and fault tolerance
"""

import hashlib
import time
import threading
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from src.core.data_structures import FileTransfer, TransferStatus, NodeStatus
from src.core.storage_node import StorageVirtualNode
from src.monitoring.heartbeat_monitor import HeartbeatMonitor
from src.replication.replication_manager import ReplicationManager
from src.utils.logger import get_logger
from src.utils.config_loader import get_config

logger = get_logger(__name__)


class StorageVirtualNetwork:
    """
    Enhanced network coordinator with:
    - Replication management (3x default)
    - Heartbeat monitoring
    - Automatic failure recovery
    - Load balancing
    - Thread-safe operations
    
    This is the MASTER/COORDINATOR (like HDFS NameNode)
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize storage network coordinator
        
        Args:
            config_path: Path to configuration file
        """
        self.config = get_config(config_path)
        
        # Node registry
        self.nodes: Dict[str, StorageVirtualNode] = {}
        
        # Transfer tracking
        self.transfer_operations: Dict[str, Dict[str, FileTransfer]] = defaultdict(dict)
        self.completed_transfers: Dict[str, FileTransfer] = {}
        
        # Replication manager
        self.replication_manager = ReplicationManager(config_path)
        
        # Heartbeat monitor
        self.heartbeat_monitor = HeartbeatMonitor(config_path)
        
        # Register callbacks
        self.heartbeat_monitor.register_failure_callback(self.handle_node_failure)
        self.heartbeat_monitor.register_recovery_callback(self.handle_node_recovery)
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Statistics
        self.total_transfers = 0
        self.failed_transfers = 0
        self.start_time = time.time()
        
        logger.info("StorageVirtualNetwork initialized")
    
    def start(self):
        """Start the network coordinator"""
        self.heartbeat_monitor.start()
        logger.info("StorageVirtualNetwork started")
    
    def stop(self):
        """Stop the network coordinator"""
        self.heartbeat_monitor.stop()
        
        # Shutdown all nodes
        for node in self.nodes.values():
            node.shutdown()
        
        logger.info("StorageVirtualNetwork stopped")
    
    def add_node(self, node: StorageVirtualNode):
        """
        Add a storage node to the network
        
        Args:
            node: StorageVirtualNode instance
        """
        with self.lock:
            self.nodes[node.node_id] = node
        
        # Start node heartbeat
        node.start_heartbeat(
            callback=self.heartbeat_monitor.receive_heartbeat,
            interval=self.config.monitoring.heartbeat_interval
        )
        
        logger.info(
            f"Node {node.node_id} added to network "
            f"({node.total_storage / (1024**3):.1f}GB storage, "
            f"{node.bandwidth / 1000000:.0f}Mbps bandwidth)"
        )
    
    def remove_node(self, node_id: str):
        """
        Remove a node from the network
        
        Args:
            node_id: Node identifier
        """
        with self.lock:
            if node_id in self.nodes:
                node = self.nodes[node_id]
                node.shutdown()
                del self.nodes[node_id]
                
                logger.info(f"Node {node_id} removed from network")
    
    def connect_nodes(self, node1_id: str, node2_id: str, bandwidth: int) -> bool:
        """
        Connect two nodes with specified bandwidth
        
        Args:
            node1_id: First node ID
            node2_id: Second node ID
            bandwidth: Connection bandwidth in Mbps
        
        Returns:
            True if successful, False otherwise
        """
        with self.lock:
            if node1_id in self.nodes and node2_id in self.nodes:
                self.nodes[node1_id].add_connection(node2_id, bandwidth)
                self.nodes[node2_id].add_connection(node1_id, bandwidth)
                
                logger.info(
                    f"Connected {node1_id} <-> {node2_id} "
                    f"({bandwidth}Mbps)"
                )
                return True
        
        logger.warning(f"Failed to connect {node1_id} and {node2_id}")
        return False
    
    def get_healthy_nodes(self) -> List[StorageVirtualNode]:
        """Get list of healthy nodes"""
        healthy_node_ids = self.heartbeat_monitor.get_healthy_nodes()
        
        with self.lock:
            return [
                self.nodes[node_id]
                for node_id in healthy_node_ids
                if node_id in self.nodes
            ]
    
    def select_target_nodes(
        self,
        file_size: int,
        replication_factor: int = None,
        exclude_nodes: Set[str] = None
    ) -> List[StorageVirtualNode]:
        """
        Select target nodes for file storage
        
        Args:
            file_size: Size of file to store
            replication_factor: Number of replicas (uses config default if None)
            exclude_nodes: Nodes to exclude from selection
        
        Returns:
            List of selected nodes
        """
        if replication_factor is None:
            replication_factor = self.config.replication.default_factor
        
        # Get healthy nodes with enough space
        healthy_nodes = self.get_healthy_nodes()
        
        # Select nodes using replication manager
        selected = self.replication_manager.select_replica_nodes(
            available_nodes=healthy_nodes,
            count=replication_factor,
            exclude_nodes=exclude_nodes or set(),
            chunk_size=file_size
        )
        
        if len(selected) < replication_factor:
            logger.warning(
                f"Could only select {len(selected)} nodes "
                f"(requested {replication_factor})"
            )
        
        return selected
    
    def initiate_file_transfer_with_replication(
        self,
        file_name: str,
        file_data: bytes,
        replication_factor: int = None,
        source_node_id: str = None
    ) -> Optional[str]:
        """
        Initiate a file transfer with replication
        
        Args:
            file_name: Name of the file
            file_data: Actual file data (bytes)
            replication_factor: Number of replicas (uses config default if None)
            source_node_id: Source node ID (optional)
        
        Returns:
            File ID if successful, None otherwise
        """
        file_size = len(file_data)
        
        if replication_factor is None:
            replication_factor = self.config.replication.default_factor
        
        # Generate unique file ID
        file_id = hashlib.sha256(
            f"{file_name}-{time.time()}".encode()
        ).hexdigest()[:16]
        
        # Select target nodes
        target_nodes = self.select_target_nodes(
            file_size=file_size,
            replication_factor=replication_factor
        )
        
        if not target_nodes:
            logger.error(f"No nodes available for file {file_name}")
            return None
        
        logger.info(
            f"Initiating transfer: {file_name} ({file_size} bytes) "
            f"to {len(target_nodes)} nodes with {replication_factor}x replication"
        )
        
        # Initiate transfer on each target node
        transfers = []
        for node in target_nodes:
            transfer = node.initiate_file_transfer(
                file_id=file_id,
                file_name=file_name,
                file_data=file_data,
                source_node=source_node_id,
                replication_factor=replication_factor
            )
            
            if transfer:
                transfers.append((node, transfer))
                
                # Register chunks with replication manager
                for chunk in transfer.chunks:
                    self.replication_manager.register_chunk(
                        file_id=file_id,
                        chunk_id=chunk.chunk_id,
                        node_id=node.node_id
                    )
        
        if not transfers:
            logger.error(f"Failed to initiate transfer for {file_name}")
            return None
        
        # Track transfer
        with self.lock:
            # Store first transfer as primary
            self.transfer_operations[file_id] = {
                node.node_id: transfer
                for node, transfer in transfers
            }
            self.total_transfers += 1
        
        logger.info(
            f"Transfer {file_id} initiated on {len(transfers)} nodes: "
            f"{[n.node_id for n, _ in transfers]}"
        )

        return file_id

    def process_file_transfer(
        self,
        file_id: str,
        chunks_per_step: int = 1
    ) -> Tuple[int, bool]:
        """
        Process file transfer chunks across all replica nodes

        Args:
            file_id: File identifier
            chunks_per_step: Number of chunks to process per step

        Returns:
            Tuple of (chunks_transferred, all_complete)
        """
        with self.lock:
            if file_id not in self.transfer_operations:
                logger.warning(f"No active transfer for {file_id}")
                return (0, False)

            node_transfers = self.transfer_operations[file_id]

        total_chunks_transferred = 0
        all_nodes_complete = True

        # Process chunks on each node
        for node_id, transfer in list(node_transfers.items()):
            if node_id not in self.nodes:
                logger.warning(f"Node {node_id} not found, skipping")
                continue

            node = self.nodes[node_id]
            chunks_transferred = 0

            # Process pending chunks
            for chunk in transfer.chunks:
                if chunk.status != TransferStatus.COMPLETED and chunks_transferred < chunks_per_step:
                    # Process chunk transfer
                    success = node.process_chunk_transfer(
                        file_id=file_id,
                        chunk_id=chunk.chunk_id,
                        source_node=transfer.source_node or "client"
                    )

                    if success:
                        chunks_transferred += 1
                        total_chunks_transferred += 1
                    else:
                        logger.warning(
                            f"Failed to transfer chunk {chunk.chunk_id} "
                            f"to node {node_id}"
                        )

            # Check if this node's transfer is complete
            if transfer.status != TransferStatus.COMPLETED:
                all_nodes_complete = False

        # If all nodes complete, mark transfer as done
        if all_nodes_complete:
            with self.lock:
                self.completed_transfers[file_id] = list(node_transfers.values())[0]
                del self.transfer_operations[file_id]

            logger.info(f"Transfer {file_id} completed on all nodes")

        return (total_chunks_transferred, all_nodes_complete)

    def handle_node_failure(self, failed_node_id: str):
        """
        Handle node failure - identify and re-replicate under-replicated chunks

        Args:
            failed_node_id: ID of failed node
        """
        logger.error(f"🚨 HANDLING NODE FAILURE: {failed_node_id}")

        # Find under-replicated chunks
        under_replicated = self.replication_manager.handle_node_failure(failed_node_id)

        if not under_replicated:
            logger.info(f"No under-replicated chunks after {failed_node_id} failure")
            return

        logger.warning(
            f"Found {len(under_replicated)} under-replicated chunks, "
            "initiating re-replication..."
        )

        # Re-replicate each under-replicated chunk
        if self.config.monitoring.enable_auto_recovery:
            for file_id, chunk_id in under_replicated:
                self._re_replicate_chunk(file_id, chunk_id, failed_node_id)
        else:
            logger.warning("Auto-recovery disabled, chunks will remain under-replicated")

    def _re_replicate_chunk(
        self,
        file_id: str,
        chunk_id: int,
        failed_node_id: str
    ):
        """
        Re-replicate a single chunk to restore replication factor

        Args:
            file_id: File identifier
            chunk_id: Chunk identifier
            failed_node_id: ID of failed node
        """
        # Get current locations
        current_locations = self.replication_manager.get_chunk_locations(file_id, chunk_id)

        if not current_locations:
            logger.error(
                f"Cannot re-replicate {file_id}:{chunk_id} - "
                "no surviving replicas!"
            )
            return

        # Select source node (any node with the chunk)
        source_node_id = list(current_locations)[0]
        source_node = self.nodes.get(source_node_id)

        if not source_node or file_id not in source_node.stored_files:
            logger.error(
                f"Source node {source_node_id} doesn't have file {file_id}"
            )
            return

        # Get chunk data
        file_transfer = source_node.stored_files[file_id]
        chunk = file_transfer.chunks[chunk_id]

        # Calculate how many more replicas we need
        target_factor = self.config.replication.default_factor
        current_count = len(current_locations)
        needed = target_factor - current_count

        if needed <= 0:
            return

        # Select new target nodes
        target_nodes = self.replication_manager.select_replica_nodes(
            available_nodes=self.get_healthy_nodes(),
            count=needed,
            exclude_nodes=current_locations | {failed_node_id},
            chunk_size=chunk.size
        )

        if not target_nodes:
            logger.error(
                f"No nodes available for re-replication of {file_id}:{chunk_id}"
            )
            return

        # Transfer chunk to new nodes
        for target_node in target_nodes:
            # Create mini-transfer for this chunk
            success = target_node.process_chunk_transfer(
                file_id=file_id,
                chunk_id=chunk_id,
                source_node=source_node_id
            )

            if success:
                # Register new replica
                self.replication_manager.register_chunk(
                    file_id=file_id,
                    chunk_id=chunk_id,
                    node_id=target_node.node_id
                )

                logger.info(
                    f"✅ Re-replicated {file_id}:{chunk_id} "
                    f"from {source_node_id} to {target_node.node_id}"
                )
            else:
                logger.error(
                    f"Failed to re-replicate {file_id}:{chunk_id} "
                    f"to {target_node.node_id}"
                )

    def handle_node_recovery(self, recovered_node_id: str):
        """
        Handle node recovery

        Args:
            recovered_node_id: ID of recovered node
        """
        logger.info(f"✅ Node {recovered_node_id} recovered")

        # Could implement rebalancing here in the future
        # For now, just log the recovery

    def get_network_stats(self) -> Dict:
        """Get comprehensive network statistics"""
        with self.lock:
            nodes_list = list(self.nodes.values())

        if not nodes_list:
            return {
                "total_nodes": 0,
                "healthy_nodes": 0,
                "failed_nodes": 0,
                "total_bandwidth_bps": 0,
                "used_bandwidth_bps": 0,
                "total_storage_bytes": 0,
                "used_storage_bytes": 0,
                "active_transfers": 0,
                "completed_transfers": len(self.completed_transfers)
            }

        total_bandwidth = sum(n.bandwidth for n in nodes_list)
        used_bandwidth = sum(n.network_utilization for n in nodes_list)
        total_storage = sum(n.total_storage for n in nodes_list)
        used_storage = sum(n.used_storage for n in nodes_list)

        heartbeat_stats = self.heartbeat_monitor.get_statistics()
        replication_stats = self.replication_manager.get_statistics()

        return {
            "total_nodes": len(nodes_list),
            "healthy_nodes": heartbeat_stats["healthy_nodes"],
            "failed_nodes": heartbeat_stats["failed_nodes"],
            "total_bandwidth_bps": total_bandwidth,
            "used_bandwidth_bps": used_bandwidth,
            "bandwidth_utilization": (used_bandwidth / total_bandwidth * 100) if total_bandwidth > 0 else 0,
            "total_storage_bytes": total_storage,
            "used_storage_bytes": used_storage,
            "storage_utilization": (used_storage / total_storage * 100) if total_storage > 0 else 0,
            "active_transfers": sum(len(t) for t in self.transfer_operations.values()),
            "completed_transfers": len(self.completed_transfers),
            "total_transfers": self.total_transfers,
            "failed_transfers": self.failed_transfers,
            "replication": replication_stats,
            "monitoring": heartbeat_stats
        }

    def __repr__(self) -> str:
        """String representation"""
        stats = self.get_network_stats()
        return (
            f"StorageVirtualNetwork("
            f"nodes={stats['total_nodes']}, "
            f"healthy={stats['healthy_nodes']}, "
            f"storage={stats['storage_utilization']:.1f}%)"
        )
