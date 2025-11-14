"""
Core Data Structures
Enhanced data structures with real checksums and replication support
"""

import time
import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Set
from enum import Enum, auto


class TransferStatus(Enum):
    """Status of file transfer or chunk transfer"""
    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


class NodeStatus(Enum):
    """Status of storage node"""
    HEALTHY = auto()
    DEGRADED = auto()
    FAILED = auto()
    RECOVERING = auto()
    OFFLINE = auto()


@dataclass
class FileChunk:
    """
    Represents a chunk of a file with real data and checksum
    
    CRITICAL IMPROVEMENT: Now stores actual data and computes real checksums
    """
    chunk_id: int
    size: int  # in bytes
    data: bytes  # ADDED: Actual chunk data
    checksum: str  # Real checksum computed from data
    status: TransferStatus = TransferStatus.PENDING
    stored_nodes: Set[str] = field(default_factory=set)  # CHANGED: Multiple nodes for replication
    created_at: float = field(default_factory=time.time)
    
    def verify_integrity(self, algorithm: str = "sha256") -> bool:
        """
        Verify chunk data integrity by recomputing checksum
        
        Returns:
            True if checksum matches, False otherwise
        """
        if algorithm == "md5":
            computed = hashlib.md5(self.data).hexdigest()
        elif algorithm == "sha1":
            computed = hashlib.sha1(self.data).hexdigest()
        elif algorithm == "sha256":
            computed = hashlib.sha256(self.data).hexdigest()
        elif algorithm == "sha512":
            computed = hashlib.sha512(self.data).hexdigest()
        else:
            raise ValueError(f"Unsupported checksum algorithm: {algorithm}")
        
        return computed == self.checksum
    
    @staticmethod
    def compute_checksum(data: bytes, algorithm: str = "sha256") -> str:
        """
        Compute checksum for given data
        
        Args:
            data: Bytes to compute checksum for
            algorithm: Hash algorithm (md5, sha1, sha256, sha512)
        
        Returns:
            Hexadecimal checksum string
        """
        if algorithm == "md5":
            return hashlib.md5(data).hexdigest()
        elif algorithm == "sha1":
            return hashlib.sha1(data).hexdigest()
        elif algorithm == "sha256":
            return hashlib.sha256(data).hexdigest()
        elif algorithm == "sha512":
            return hashlib.sha512(data).hexdigest()
        else:
            raise ValueError(f"Unsupported checksum algorithm: {algorithm}")
    
    def get_replication_count(self) -> int:
        """Get number of replicas for this chunk"""
        return len(self.stored_nodes)
    
    def is_under_replicated(self, target_replication: int) -> bool:
        """Check if chunk has fewer replicas than target"""
        return self.get_replication_count() < target_replication


@dataclass
class FileMetadata:
    """Metadata describing a stored file (used by distributed nodes)."""

    file_id: str
    file_name: str
    total_size: int
    chunk_count: int
    replication_factor: int = 3
    checksum: Optional[str] = None
    created_at: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> dict:
        """Serialize metadata to a dictionary for logging or network responses."""
        return {
            "file_id": self.file_id,
            "file_name": self.file_name,
            "total_size": self.total_size,
            "chunk_count": self.chunk_count,
            "replication_factor": self.replication_factor,
            "checksum": self.checksum,
            "created_at": self.created_at,
        }


@dataclass
class FileTransfer:
    """
    Represents a file transfer operation with multiple chunks
    """
    file_id: str
    file_name: str
    total_size: int  # in bytes
    chunks: List[FileChunk] = field(default_factory=list)
    status: TransferStatus = TransferStatus.PENDING
    created_at: float = field(default_factory=lambda: time.time())
    completed_at: Optional[float] = None
    source_node: Optional[str] = None
    target_nodes: Set[str] = field(default_factory=set)  # Multiple targets for replication
    replication_factor: int = 3  # ADDED: Target replication factor
    
    def get_progress(self) -> float:
        """
        Get transfer progress as percentage
        
        Returns:
            Progress percentage (0.0 to 100.0)
        """
        if not self.chunks:
            return 0.0
        
        completed_chunks = sum(
            1 for chunk in self.chunks 
            if chunk.status == TransferStatus.COMPLETED
        )
        return (completed_chunks / len(self.chunks)) * 100.0
    
    def get_completed_chunks(self) -> int:
        """Get number of completed chunks"""
        return sum(
            1 for chunk in self.chunks 
            if chunk.status == TransferStatus.COMPLETED
        )
    
    def get_failed_chunks(self) -> List[FileChunk]:
        """Get list of failed chunks"""
        return [
            chunk for chunk in self.chunks 
            if chunk.status == TransferStatus.FAILED
        ]
    
    def is_complete(self) -> bool:
        """Check if all chunks are completed"""
        return all(
            chunk.status == TransferStatus.COMPLETED 
            for chunk in self.chunks
        )
    
    def get_duration(self) -> Optional[float]:
        """Get transfer duration in seconds"""
        if self.completed_at:
            return self.completed_at - self.created_at
        return None
    
    def get_throughput(self) -> Optional[float]:
        """
        Get transfer throughput in MB/s
        
        Returns:
            Throughput in MB/s or None if not completed
        """
        duration = self.get_duration()
        if duration and duration > 0:
            mb_transferred = self.total_size / (1024 * 1024)
            return mb_transferred / duration
        return None
    
    def verify_all_chunks(self, algorithm: str = "sha256") -> bool:
        """
        Verify integrity of all chunks
        
        Returns:
            True if all chunks are valid, False otherwise
        """
        return all(chunk.verify_integrity(algorithm) for chunk in self.chunks)
    
    def get_under_replicated_chunks(self) -> List[FileChunk]:
        """Get list of chunks that are under-replicated"""
        return [
            chunk for chunk in self.chunks
            if chunk.is_under_replicated(self.replication_factor)
        ]


@dataclass
class NodeMetrics:
    """
    Performance metrics for a storage node
    """
    node_id: str
    timestamp: float = field(default_factory=time.time)
    
    # Storage metrics
    total_storage_bytes: int = 0
    used_storage_bytes: int = 0
    available_storage_bytes: int = 0
    storage_utilization_percent: float = 0.0
    
    # Network metrics
    total_bandwidth_bps: int = 0
    used_bandwidth_bps: int = 0
    available_bandwidth_bps: int = 0
    bandwidth_utilization_percent: float = 0.0
    
    # Transfer metrics
    active_transfers: int = 0
    completed_transfers: int = 0
    failed_transfers: int = 0
    total_data_transferred_bytes: int = 0
    
    # Replication metrics
    chunks_stored: int = 0
    unique_files: int = 0
    replication_factor_avg: float = 0.0
    
    # Performance metrics
    avg_transfer_speed_mbps: float = 0.0
    uptime_seconds: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert metrics to dictionary"""
        return {
            "node_id": self.node_id,
            "timestamp": self.timestamp,
            "storage": {
                "total_bytes": self.total_storage_bytes,
                "used_bytes": self.used_storage_bytes,
                "available_bytes": self.available_storage_bytes,
                "utilization_percent": self.storage_utilization_percent
            },
            "network": {
                "total_bandwidth_bps": self.total_bandwidth_bps,
                "used_bandwidth_bps": self.used_bandwidth_bps,
                "available_bandwidth_bps": self.available_bandwidth_bps,
                "utilization_percent": self.bandwidth_utilization_percent
            },
            "transfers": {
                "active": self.active_transfers,
                "completed": self.completed_transfers,
                "failed": self.failed_transfers,
                "total_data_bytes": self.total_data_transferred_bytes
            },
            "replication": {
                "chunks_stored": self.chunks_stored,
                "unique_files": self.unique_files,
                "avg_replication_factor": self.replication_factor_avg
            },
            "performance": {
                "avg_speed_mbps": self.avg_transfer_speed_mbps,
                "uptime_seconds": self.uptime_seconds
            }
        }


@dataclass
class HeartbeatMessage:
    """
    Heartbeat message sent by nodes to coordinator
    """
    node_id: str
    timestamp: float = field(default_factory=time.time)
    status: NodeStatus = NodeStatus.HEALTHY
    metrics: Optional[NodeMetrics] = None
    
    def is_recent(self, timeout_seconds: int = 30) -> bool:
        """Check if heartbeat is recent (within timeout)"""
        return (time.time() - self.timestamp) < timeout_seconds

