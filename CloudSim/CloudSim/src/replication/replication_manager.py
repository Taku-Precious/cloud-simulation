"""
Replication Manager
Manages data replication across storage nodes for fault tolerance
"""

import threading
import time
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict
import random

from src.core.data_structures import FileChunk, FileTransfer, TransferStatus
from src.utils.logger import get_logger
from src.utils.config_loader import get_config

logger = get_logger(__name__)


class ReplicationManager:
    """
    Manages data replication across storage nodes
    
    Features:
    - Intelligent replica placement (diverse nodes)
    - Automatic re-replication on node failure
    - Under-replication detection
    - Load-balanced replica placement
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize replication manager
        
        Args:
            config_path: Path to configuration file
        """
        self.config = get_config(config_path)
        
        # Chunk location tracking
        # chunk_key (file_id:chunk_id) -> set of node_ids
        self.chunk_locations: Dict[str, Set[str]] = defaultdict(set)
        
        # File metadata
        # file_id -> FileTransfer
        self.file_metadata: Dict[str, FileTransfer] = {}
        
        # Replication queue (chunks that need re-replication)
        self.replication_queue: List[Tuple[str, int, int]] = []  # (file_id, chunk_id, target_count)
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Statistics
        self.total_replications = 0
        self.total_re_replications = 0
        self.under_replicated_chunks = 0
        
        logger.info(
            f"ReplicationManager initialized: "
            f"default_factor={self.config.replication.default_factor}, "
            f"strategy={self.config.replication.placement_strategy}"
        )
    
    def register_chunk(self, file_id: str, chunk_id: int, node_id: str):
        """
        Register a chunk replica on a node
        
        Args:
            file_id: File identifier
            chunk_id: Chunk identifier
            node_id: Node storing the chunk
        """
        chunk_key = f"{file_id}:{chunk_id}"
        
        with self.lock:
            self.chunk_locations[chunk_key].add(node_id)
            self.total_replications += 1
        
        logger.debug(
            f"Registered chunk {chunk_key} on node {node_id} "
            f"(replicas: {len(self.chunk_locations[chunk_key])})"
        )
    
    def unregister_chunk(self, file_id: str, chunk_id: int, node_id: str):
        """
        Unregister a chunk replica from a node (e.g., node failure)
        
        Args:
            file_id: File identifier
            chunk_id: Chunk identifier
            node_id: Node that lost the chunk
        """
        chunk_key = f"{file_id}:{chunk_id}"
        
        with self.lock:
            if chunk_key in self.chunk_locations:
                self.chunk_locations[chunk_key].discard(node_id)
                
                remaining = len(self.chunk_locations[chunk_key])
                logger.warning(
                    f"Unregistered chunk {chunk_key} from node {node_id} "
                    f"(remaining replicas: {remaining})"
                )
                
                # Check if under-replicated
                if remaining < self.config.replication.min_factor:
                    self.under_replicated_chunks += 1
                    logger.error(
                        f"⚠️  UNDER-REPLICATED: {chunk_key} has only {remaining} replicas "
                        f"(minimum: {self.config.replication.min_factor})"
                    )
    
    def get_chunk_locations(self, file_id: str, chunk_id: int) -> Set[str]:
        """
        Get all nodes storing a specific chunk
        
        Args:
            file_id: File identifier
            chunk_id: Chunk identifier
        
        Returns:
            Set of node IDs storing the chunk
        """
        chunk_key = f"{file_id}:{chunk_id}"
        with self.lock:
            return self.chunk_locations.get(chunk_key, set()).copy()
    
    def get_replication_count(self, file_id: str, chunk_id: int) -> int:
        """Get number of replicas for a chunk"""
        return len(self.get_chunk_locations(file_id, chunk_id))
    
    def is_under_replicated(self, file_id: str, chunk_id: int) -> bool:
        """Check if a chunk is under-replicated"""
        count = self.get_replication_count(file_id, chunk_id)
        return count < self.config.replication.min_factor
    
    def select_replica_nodes(
        self,
        available_nodes: List,  # List of StorageVirtualNode
        count: int,
        exclude_nodes: Set[str] = None,
        chunk_size: int = 0
    ) -> List:
        """
        Select nodes for replica placement using configured strategy
        
        Args:
            available_nodes: List of available storage nodes
            count: Number of nodes to select
            exclude_nodes: Nodes to exclude from selection
            chunk_size: Size of chunk to store (for capacity check)
        
        Returns:
            List of selected nodes
        """
        if exclude_nodes is None:
            exclude_nodes = set()
        
        # Filter nodes
        candidates = [
            node for node in available_nodes
            if node.node_id not in exclude_nodes
            and node.total_storage - node.used_storage >= chunk_size
        ]
        
        if len(candidates) < count:
            logger.warning(
                f"Not enough nodes for replication: need {count}, "
                f"have {len(candidates)}"
            )
            return candidates
        
        # Apply placement strategy
        strategy = self.config.replication.placement_strategy
        
        if strategy == "random":
            selected = random.sample(candidates, count)
        
        elif strategy == "least_loaded":
            # Sort by available storage (descending)
            candidates.sort(
                key=lambda n: n.total_storage - n.used_storage,
                reverse=True
            )
            selected = candidates[:count]
        
        elif strategy == "diverse":
            # Try to maximize diversity (simple heuristic: spread across nodes)
            # Sort by available storage first
            candidates.sort(
                key=lambda n: n.total_storage - n.used_storage,
                reverse=True
            )
            
            # Select every Nth node to maximize spread
            step = max(1, len(candidates) // count)
            selected = []
            for i in range(0, len(candidates), step):
                if len(selected) >= count:
                    break
                selected.append(candidates[i])
            
            # Fill remaining with least loaded
            while len(selected) < count and len(selected) < len(candidates):
                for node in candidates:
                    if node not in selected:
                        selected.append(node)
                        break
        
        else:
            logger.warning(f"Unknown placement strategy: {strategy}, using random")
            selected = random.sample(candidates, count)
        
        logger.debug(
            f"Selected {len(selected)} nodes for replication "
            f"(strategy={strategy}): {[n.node_id for n in selected]}"
        )
        
        return selected
    
    def find_chunks_on_node(self, node_id: str) -> List[Tuple[str, int]]:
        """
        Find all chunks stored on a specific node
        
        Args:
            node_id: Node identifier
        
        Returns:
            List of (file_id, chunk_id) tuples
        """
        chunks = []
        
        with self.lock:
            for chunk_key, nodes in self.chunk_locations.items():
                if node_id in nodes:
                    file_id, chunk_id = chunk_key.split(':')
                    chunks.append((file_id, int(chunk_id)))
        
        logger.info(f"Found {len(chunks)} chunks on node {node_id}")
        return chunks
    
    def handle_node_failure(self, failed_node_id: str) -> List[Tuple[str, int]]:
        """
        Handle node failure by identifying under-replicated chunks
        
        Args:
            failed_node_id: ID of failed node
        
        Returns:
            List of (file_id, chunk_id) that need re-replication
        """
        logger.warning(f"Handling failure of node {failed_node_id}")
        
        under_replicated = []
        
        # Find all chunks on failed node
        chunks_on_node = self.find_chunks_on_node(failed_node_id)
        
        # Unregister each chunk and check replication
        for file_id, chunk_id in chunks_on_node:
            self.unregister_chunk(file_id, chunk_id, failed_node_id)
            
            # Check if now under-replicated
            if self.is_under_replicated(file_id, chunk_id):
                under_replicated.append((file_id, chunk_id))
                
                # Add to replication queue
                target_count = self.config.replication.default_factor
                current_count = self.get_replication_count(file_id, chunk_id)
                needed = target_count - current_count
                
                self.replication_queue.append((file_id, chunk_id, needed))
        
        logger.warning(
            f"Node {failed_node_id} failure: {len(chunks_on_node)} chunks affected, "
            f"{len(under_replicated)} under-replicated"
        )
        
        return under_replicated
    
    def get_statistics(self) -> Dict:
        """Get replication statistics"""
        with self.lock:
            total_chunks = len(self.chunk_locations)
            total_replicas = sum(len(nodes) for nodes in self.chunk_locations.values())
            avg_replication = total_replicas / total_chunks if total_chunks > 0 else 0
            
            under_replicated = sum(
                1 for chunk_key in self.chunk_locations
                if len(self.chunk_locations[chunk_key]) < self.config.replication.min_factor
            )
            
            return {
                "total_chunks": total_chunks,
                "total_replicas": total_replicas,
                "avg_replication_factor": avg_replication,
                "under_replicated_chunks": under_replicated,
                "replication_queue_size": len(self.replication_queue),
                "total_replications": self.total_replications,
                "total_re_replications": self.total_re_replications
            }
    
    def __repr__(self) -> str:
        """String representation"""
        stats = self.get_statistics()
        return (
            f"ReplicationManager("
            f"chunks={stats['total_chunks']}, "
            f"avg_factor={stats['avg_replication_factor']:.2f}, "
            f"under_replicated={stats['under_replicated_chunks']})"
        )

