"""
Storage Virtual Node - Enhanced Version
Production-grade storage node with replication, fault tolerance, and monitoring
"""

import time
import math
import threading
import random
from typing import Dict, List, Optional, Set
from collections import defaultdict

from src.core.data_structures import (
    FileChunk, FileTransfer, TransferStatus, NodeStatus,
    NodeMetrics, HeartbeatMessage
)
from src.utils.logger import get_logger
from src.utils.config_loader import get_config

logger = get_logger(__name__)


class StorageVirtualNode:
    """
    Enhanced storage node with:
    - Real checksums (SHA-256)
    - Thread-safe operations
    - Bandwidth tracking (FIXED BUG)
    - Replication support
    - Heartbeat monitoring
    - Performance metrics
    """
    
    def __init__(
        self,
        node_id: str,
        cpu_capacity: int,  # in vCPUs
        memory_capacity: int,  # in GB
        storage_capacity: int,  # in GB
        bandwidth: int,  # in Mbps
        config_path: str = "config.yaml"
    ):
        self.node_id = node_id
        self.cpu_capacity = cpu_capacity
        self.memory_capacity = memory_capacity
        self.total_storage = storage_capacity * 1024 * 1024 * 1024  # Convert GB to bytes
        self.bandwidth = bandwidth * 1000000  # Convert Mbps to bits per second
        
        # Load configuration
        self.config = get_config(config_path)
        
        # Current utilization
        self.used_storage = 0
        self.active_transfers: Dict[str, FileTransfer] = {}
        self.stored_files: Dict[str, FileTransfer] = {}
        
        # FIXED: Network utilization tracking per transfer
        self.active_bandwidth_usage: Dict[str, float] = {}  # transfer_key -> bandwidth
        self.network_utilization = 0.0  # Total current bandwidth usage
        
        # Performance metrics
        self.total_requests_processed = 0
        self.total_data_transferred = 0  # in bytes
        self.failed_transfers = 0
        self.start_time = time.time()
        
        # Network connections (node_id: bandwidth_available)
        self.connections: Dict[str, int] = {}
        
        # Thread safety
        self.transfer_lock = threading.RLock()  # Reentrant lock
        self.storage_lock = threading.Lock()
        self.bandwidth_lock = threading.Lock()
        
        # Node status
        self.status = NodeStatus.HEALTHY
        self.last_heartbeat = time.time()
        
        # Heartbeat thread
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.heartbeat_callback = None
        self.running = False
        
        logger.info(
            f"Node {node_id} initialized: "
            f"{storage_capacity}GB storage, {bandwidth}Mbps bandwidth"
        )
    
    def add_connection(self, node_id: str, bandwidth: int):
        """Add a network connection to another node"""
        self.connections[node_id] = bandwidth * 1000000  # Store in bits per second
        logger.debug(f"Node {self.node_id} connected to {node_id} with {bandwidth}Mbps")
    
    def _calculate_chunk_size(self, file_size: int) -> int:
        """
        Determine optimal chunk size based on file size
        Uses configuration values
        """
        chunking = self.config.chunking
        
        if file_size < chunking.small_file_threshold:
            return chunking.small_chunk_size
        elif file_size < chunking.medium_file_threshold:
            return chunking.medium_chunk_size
        else:
            return chunking.large_chunk_size
    
    def _generate_chunks(
        self, 
        file_data: bytes, 
        file_id: str, 
        file_size: int
    ) -> List[FileChunk]:
        """
        Break file into chunks with REAL checksums
        
        CRITICAL FIX: Now computes checksums from actual data, not metadata
        """
        chunk_size = self._calculate_chunk_size(file_size)
        num_chunks = math.ceil(file_size / chunk_size)
        algorithm = self.config.storage.checksum_algorithm
        
        chunks = []
        for i in range(num_chunks):
            start = i * chunk_size
            end = min(start + chunk_size, file_size)
            chunk_data = file_data[start:end]
            
            # REAL checksum from actual data
            real_checksum = FileChunk.compute_checksum(chunk_data, algorithm)
            
            chunk = FileChunk(
                chunk_id=i,
                size=len(chunk_data),
                data=chunk_data,  # Store actual data
                checksum=real_checksum  # Real checksum
            )
            chunks.append(chunk)
        
        logger.debug(
            f"Generated {num_chunks} chunks for file {file_id} "
            f"(chunk_size={chunk_size}, algorithm={algorithm})"
        )
        
        return chunks
    
    def initiate_file_transfer(
        self,
        file_id: str,
        file_name: str,
        file_data: bytes,  # CHANGED: Now requires actual data
        source_node: Optional[str] = None,
        replication_factor: int = None
    ) -> Optional[FileTransfer]:
        """
        Initiate a file storage request to this node
        
        Args:
            file_id: Unique file identifier
            file_name: Name of the file
            file_data: Actual file data (bytes)
            source_node: Source node ID (optional)
            replication_factor: Target replication factor
        
        Returns:
            FileTransfer object or None if insufficient space
        """
        file_size = len(file_data)
        
        if replication_factor is None:
            replication_factor = self.config.replication.default_factor
        
        # Check if we have enough storage space
        with self.storage_lock:
            if self.used_storage + file_size > self.total_storage:
                logger.warning(
                    f"Node {self.node_id}: Insufficient storage for {file_name} "
                    f"({file_size} bytes needed, {self.total_storage - self.used_storage} available)"
                )
                return None
        
        # Create file transfer record with real chunks
        chunks = self._generate_chunks(file_data, file_id, file_size)
        
        transfer = FileTransfer(
            file_id=file_id,
            file_name=file_name,
            total_size=file_size,
            chunks=chunks,
            source_node=source_node,
            replication_factor=replication_factor
        )
        
        with self.transfer_lock:
            self.active_transfers[file_id] = transfer
        
        logger.info(
            f"Node {self.node_id}: Initiated transfer for {file_name} "
            f"({file_size} bytes, {len(chunks)} chunks, {replication_factor}x replication)"
        )

        return transfer

    def process_chunk_transfer(
        self,
        file_id: str,
        chunk_id: int,
        source_node: str
    ) -> bool:
        """
        Process an incoming file chunk

        CRITICAL FIX: Network utilization now properly tracked and decremented
        """
        with self.transfer_lock:
            if file_id not in self.active_transfers:
                logger.warning(f"Node {self.node_id}: No active transfer for {file_id}")
                return False

            transfer = self.active_transfers[file_id]

        try:
            chunk = next(c for c in transfer.chunks if c.chunk_id == chunk_id)
        except StopIteration:
            logger.error(f"Node {self.node_id}: Chunk {chunk_id} not found in {file_id}")
            return False

        # Verify checksum if enabled
        if self.config.storage.verify_on_write:
            if not chunk.verify_integrity(self.config.storage.checksum_algorithm):
                logger.error(
                    f"Node {self.node_id}: Checksum verification failed for "
                    f"chunk {chunk_id} of {file_id}"
                )
                chunk.status = TransferStatus.FAILED
                return False

        # Simulate network transfer time
        chunk_size_bits = chunk.size * 8  # Convert bytes to bits

        with self.bandwidth_lock:
            # If source is client or not in connections, use full node bandwidth
            connection_bandwidth = self.connections.get(source_node, self.bandwidth)
            available_bandwidth = min(
                self.bandwidth - self.network_utilization,
                connection_bandwidth
            )

        if available_bandwidth <= 0:
            logger.warning(
                f"Node {self.node_id}: No bandwidth available for transfer "
                f"(utilization: {self.network_utilization}/{self.bandwidth})"
            )
            return False

        # Calculate transfer time (in seconds)
        transfer_time = chunk_size_bits / available_bandwidth

        # Add latency simulation if enabled
        if self.config.testing.enable_latency_simulation:
            latency = self.config.testing.base_latency_ms / 1000.0  # Convert to seconds
            transfer_time += latency

        # Simulate transfer delay
        time.sleep(transfer_time)

        # CRITICAL FIX: Track bandwidth per transfer
        transfer_key = f"{file_id}_{chunk_id}"
        bandwidth_used = available_bandwidth * 0.8  # 80% utilization during transfer

        with self.bandwidth_lock:
            self.active_bandwidth_usage[transfer_key] = bandwidth_used
            self.network_utilization = sum(self.active_bandwidth_usage.values())

        # Update chunk status
        chunk.status = TransferStatus.COMPLETED
        chunk.stored_nodes.add(self.node_id)

        # Update metrics
        self.total_data_transferred += chunk.size

        logger.debug(
            f"Node {self.node_id}: Completed chunk {chunk_id} of {file_id} "
            f"({chunk.size} bytes in {transfer_time:.3f}s)"
        )

        # Check if all chunks are completed
        with self.transfer_lock:
            if all(c.status == TransferStatus.COMPLETED for c in transfer.chunks):
                transfer.status = TransferStatus.COMPLETED
                transfer.completed_at = time.time()

                with self.storage_lock:
                    self.used_storage += transfer.total_size

                self.stored_files[file_id] = transfer
                del self.active_transfers[file_id]
                self.total_requests_processed += 1

                # CRITICAL FIX: Release bandwidth for all chunks of this file
                with self.bandwidth_lock:
                    for i in range(len(transfer.chunks)):
                        key = f"{file_id}_{i}"
                        self.active_bandwidth_usage.pop(key, None)
                    self.network_utilization = sum(self.active_bandwidth_usage.values())

                duration = transfer.get_duration()
                throughput = transfer.get_throughput()
                logger.info(
                    f"Node {self.node_id}: Transfer {file_id} completed "
                    f"({transfer.total_size} bytes in {duration:.2f}s, "
                    f"throughput: {throughput:.2f} MB/s)"
                )

        return True

    def complete_chunk_transfer(self, file_id: str, chunk_id: int):
        """
        Mark a chunk transfer as complete and release bandwidth

        CRITICAL FIX: Properly release bandwidth when chunk completes
        """
        transfer_key = f"{file_id}_{chunk_id}"

        with self.bandwidth_lock:
            if transfer_key in self.active_bandwidth_usage:
                del self.active_bandwidth_usage[transfer_key]
                self.network_utilization = sum(self.active_bandwidth_usage.values())

                logger.debug(
                    f"Node {self.node_id}: Released bandwidth for {transfer_key}, "
                    f"new utilization: {self.network_utilization}/{self.bandwidth}"
                )

    def retrieve_file(
        self,
        file_id: str,
        destination_node: str
    ) -> Optional[FileTransfer]:
        """Initiate file retrieval to another node"""
        if file_id not in self.stored_files:
            logger.warning(f"Node {self.node_id}: File {file_id} not found")
            return None

        file_transfer = self.stored_files[file_id]

        # Verify integrity before retrieval if enabled
        if self.config.storage.verify_on_read:
            if not file_transfer.verify_all_chunks(self.config.storage.checksum_algorithm):
                logger.error(
                    f"Node {self.node_id}: Integrity check failed for {file_id}, "
                    "possible data corruption"
                )
                return None

        # Create a new transfer record for the retrieval
        new_transfer = FileTransfer(
            file_id=f"retr-{file_id}-{time.time()}",
            file_name=file_transfer.file_name,
            total_size=file_transfer.total_size,
            chunks=[
                FileChunk(
                    chunk_id=c.chunk_id,
                    size=c.size,
                    data=c.data,  # Copy actual data
                    checksum=c.checksum,
                    stored_nodes={destination_node}
                )
                for c in file_transfer.chunks
            ]
        )

        logger.info(
            f"Node {self.node_id}: Initiated retrieval of {file_id} "
            f"to {destination_node}"
        )

        return new_transfer

    def get_storage_utilization(self) -> Dict:
        """Get current storage utilization metrics"""
        with self.storage_lock:
            return {
                "used_bytes": self.used_storage,
                "total_bytes": self.total_storage,
                "available_bytes": self.total_storage - self.used_storage,
                "utilization_percent": (self.used_storage / self.total_storage) * 100 if self.total_storage > 0 else 0,
                "files_stored": len(self.stored_files),
                "active_transfers": len(self.active_transfers)
            }

    def get_network_utilization(self) -> Dict:
        """Get current network utilization metrics"""
        with self.bandwidth_lock:
            return {
                "current_utilization_bps": self.network_utilization,
                "max_bandwidth_bps": self.bandwidth,
                "available_bandwidth_bps": self.bandwidth - self.network_utilization,
                "utilization_percent": (self.network_utilization / self.bandwidth) * 100 if self.bandwidth > 0 else 0,
                "connections": list(self.connections.keys()),
                "active_transfers": len(self.active_bandwidth_usage)
            }

    def get_performance_metrics(self) -> Dict:
        """Get node performance metrics"""
        uptime = time.time() - self.start_time

        return {
            "total_requests_processed": self.total_requests_processed,
            "total_data_transferred_bytes": self.total_data_transferred,
            "failed_transfers": self.failed_transfers,
            "current_active_transfers": len(self.active_transfers),
            "uptime_seconds": uptime,
            "avg_throughput_mbps": (self.total_data_transferred * 8 / uptime / 1000000) if uptime > 0 else 0
        }

    def get_metrics(self) -> NodeMetrics:
        """
        Get comprehensive node metrics

        Returns:
            NodeMetrics object with all current metrics
        """
        storage = self.get_storage_utilization()
        network = self.get_network_utilization()
        performance = self.get_performance_metrics()

        # Calculate replication metrics
        total_chunks = sum(len(f.chunks) for f in self.stored_files.values())
        total_replication = sum(
            sum(len(chunk.stored_nodes) for chunk in f.chunks)
            for f in self.stored_files.values()
        )
        avg_replication = total_replication / total_chunks if total_chunks > 0 else 0

        metrics = NodeMetrics(
            node_id=self.node_id,
            total_storage_bytes=storage["total_bytes"],
            used_storage_bytes=storage["used_bytes"],
            available_storage_bytes=storage["available_bytes"],
            storage_utilization_percent=storage["utilization_percent"],
            total_bandwidth_bps=network["max_bandwidth_bps"],
            used_bandwidth_bps=network["current_utilization_bps"],
            available_bandwidth_bps=network["available_bandwidth_bps"],
            bandwidth_utilization_percent=network["utilization_percent"],
            active_transfers=len(self.active_transfers),
            completed_transfers=self.total_requests_processed,
            failed_transfers=self.failed_transfers,
            total_data_transferred_bytes=self.total_data_transferred,
            chunks_stored=total_chunks,
            unique_files=len(self.stored_files),
            replication_factor_avg=avg_replication,
            avg_transfer_speed_mbps=performance["avg_throughput_mbps"],
            uptime_seconds=performance["uptime_seconds"]
        )

        return metrics

    def start_heartbeat(self, callback, interval: int = None):
        """
        Start sending heartbeats to coordinator

        Args:
            callback: Function to call with heartbeat message
            interval: Heartbeat interval in seconds (uses config if None)
        """
        if interval is None:
            interval = self.config.monitoring.heartbeat_interval

        self.heartbeat_callback = callback
        self.running = True

        def send_heartbeats():
            logger.info(f"Node {self.node_id}: Starting heartbeat (interval={interval}s)")

            while self.running:
                try:
                    # Create heartbeat message with metrics
                    heartbeat = HeartbeatMessage(
                        node_id=self.node_id,
                        status=self.status,
                        metrics=self.get_metrics()
                    )

                    # Send to coordinator
                    if self.heartbeat_callback:
                        self.heartbeat_callback(heartbeat)

                    self.last_heartbeat = time.time()

                except Exception as e:
                    logger.error(f"Node {self.node_id}: Heartbeat error: {e}")

                time.sleep(interval)

        self.heartbeat_thread = threading.Thread(target=send_heartbeats, daemon=True)
        self.heartbeat_thread.start()

    def stop_heartbeat(self):
        """Stop sending heartbeats"""
        self.running = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=5)
        logger.info(f"Node {self.node_id}: Heartbeat stopped")

    def shutdown(self):
        """Gracefully shutdown the node"""
        logger.info(f"Node {self.node_id}: Shutting down...")

        self.status = NodeStatus.OFFLINE
        self.stop_heartbeat()

        # Wait for active transfers to complete (with timeout)
        timeout = 30
        start = time.time()

        while self.active_transfers and (time.time() - start) < timeout:
            logger.info(
                f"Node {self.node_id}: Waiting for {len(self.active_transfers)} "
                "active transfers to complete..."
            )
            time.sleep(1)

        if self.active_transfers:
            logger.warning(
                f"Node {self.node_id}: Shutdown with {len(self.active_transfers)} "
                "incomplete transfers"
            )

        logger.info(f"Node {self.node_id}: Shutdown complete")

    def __repr__(self) -> str:
        """String representation of node"""
        storage = self.get_storage_utilization()
        return (
            f"StorageVirtualNode(id={self.node_id}, "
            f"storage={storage['utilization_percent']:.1f}%, "
            f"status={self.status.name})"
        )

