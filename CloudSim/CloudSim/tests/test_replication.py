"""
Unit tests for ReplicationManager

Tests:
- Chunk registration and tracking
- Replica placement strategies
- Under-replication detection
- Node failure handling
- Re-replication
"""

import pytest
from src.replication.replication_manager import ReplicationManager
from src.core.storage_node import StorageVirtualNode


@pytest.fixture
def replication_manager():
    """Create a test replication manager"""
    return ReplicationManager()


@pytest.fixture
def test_nodes():
    """Create test storage nodes"""
    nodes = [
        StorageVirtualNode(
            node_id=f"node-{i}",
            cpu_capacity=4,
            memory_capacity=8 * 1024**3,
            storage_capacity=100 * 1024**3,
            bandwidth=100 * 1000000
        )
        for i in range(5)
    ]
    yield nodes
    for node in nodes:
        node.shutdown()


class TestChunkRegistration:
    """Test chunk registration and tracking"""
    
    def test_register_chunk(self, replication_manager):
        """Test registering a chunk on a node"""
        replication_manager.register_chunk("file-1", 0, "node-1")
        
        locations = replication_manager.get_chunk_locations("file-1", 0)
        assert "node-1" in locations
        assert len(locations) == 1
    
    def test_register_multiple_replicas(self, replication_manager):
        """Test registering multiple replicas of same chunk"""
        replication_manager.register_chunk("file-1", 0, "node-1")
        replication_manager.register_chunk("file-1", 0, "node-2")
        replication_manager.register_chunk("file-1", 0, "node-3")
        
        locations = replication_manager.get_chunk_locations("file-1", 0)
        assert len(locations) == 3
        assert "node-1" in locations
        assert "node-2" in locations
        assert "node-3" in locations
    
    def test_replication_count(self, replication_manager):
        """Test getting replication count"""
        replication_manager.register_chunk("file-1", 0, "node-1")
        replication_manager.register_chunk("file-1", 0, "node-2")
        
        count = replication_manager.get_replication_count("file-1", 0)
        assert count == 2


class TestReplicaPlacement:
    """Test replica placement strategies"""
    
    def test_select_random_strategy(self, replication_manager, test_nodes):
        """Test random placement strategy"""
        replication_manager.config.replication.placement_strategy = "random"
        
        selected = replication_manager.select_replica_nodes(
            available_nodes=test_nodes,
            count=3,
            chunk_size=1024
        )
        
        assert len(selected) == 3
        assert all(node in test_nodes for node in selected)
    
    def test_select_least_loaded_strategy(self, replication_manager, test_nodes):
        """Test least loaded placement strategy"""
        replication_manager.config.replication.placement_strategy = "least_loaded"
        
        # Fill some nodes
        test_nodes[0].used_storage = 50 * 1024**3  # 50GB used
        test_nodes[1].used_storage = 10 * 1024**3  # 10GB used
        test_nodes[2].used_storage = 80 * 1024**3  # 80GB used
        
        selected = replication_manager.select_replica_nodes(
            available_nodes=test_nodes,
            count=2,
            chunk_size=1024
        )
        
        assert len(selected) == 2
        # Should select nodes with most available space
        assert test_nodes[1] in selected or test_nodes[3] in selected or test_nodes[4] in selected
    
    def test_select_diverse_strategy(self, replication_manager, test_nodes):
        """Test diverse placement strategy"""
        replication_manager.config.replication.placement_strategy = "diverse"
        
        selected = replication_manager.select_replica_nodes(
            available_nodes=test_nodes,
            count=3,
            chunk_size=1024
        )
        
        assert len(selected) == 3
        # All selected nodes should be different
        assert len(set(n.node_id for n in selected)) == 3
    
    def test_exclude_nodes(self, replication_manager, test_nodes):
        """Test excluding specific nodes from selection"""
        exclude = {"node-0", "node-1"}
        
        selected = replication_manager.select_replica_nodes(
            available_nodes=test_nodes,
            count=2,
            exclude_nodes=exclude,
            chunk_size=1024
        )
        
        assert len(selected) == 2
        for node in selected:
            assert node.node_id not in exclude
    
    def test_insufficient_nodes(self, replication_manager, test_nodes):
        """Test when not enough nodes available"""
        selected = replication_manager.select_replica_nodes(
            available_nodes=test_nodes[:2],  # Only 2 nodes
            count=5,  # Request 5
            chunk_size=1024
        )
        
        # Should return all available nodes
        assert len(selected) == 2


class TestUnderReplication:
    """Test under-replication detection"""
    
    def test_is_under_replicated(self, replication_manager):
        """Test detecting under-replicated chunks"""
        # Register only 1 replica (min is 2 by default)
        replication_manager.register_chunk("file-1", 0, "node-1")
        
        assert replication_manager.is_under_replicated("file-1", 0)
    
    def test_is_properly_replicated(self, replication_manager):
        """Test properly replicated chunks"""
        # Register 3 replicas (default factor)
        replication_manager.register_chunk("file-1", 0, "node-1")
        replication_manager.register_chunk("file-1", 0, "node-2")
        replication_manager.register_chunk("file-1", 0, "node-3")
        
        assert not replication_manager.is_under_replicated("file-1", 0)
    
    def test_unregister_chunk(self, replication_manager):
        """Test unregistering a chunk replica"""
        # Register 3 replicas
        replication_manager.register_chunk("file-1", 0, "node-1")
        replication_manager.register_chunk("file-1", 0, "node-2")
        replication_manager.register_chunk("file-1", 0, "node-3")
        
        # Unregister one
        replication_manager.unregister_chunk("file-1", 0, "node-1")
        
        locations = replication_manager.get_chunk_locations("file-1", 0)
        assert len(locations) == 2
        assert "node-1" not in locations


class TestNodeFailure:
    """Test node failure handling"""
    
    def test_find_chunks_on_node(self, replication_manager):
        """Test finding all chunks on a specific node"""
        # Register multiple chunks on node-1
        replication_manager.register_chunk("file-1", 0, "node-1")
        replication_manager.register_chunk("file-1", 1, "node-1")
        replication_manager.register_chunk("file-2", 0, "node-1")
        replication_manager.register_chunk("file-2", 1, "node-2")
        
        chunks = replication_manager.find_chunks_on_node("node-1")
        
        assert len(chunks) == 3
        assert ("file-1", 0) in chunks
        assert ("file-1", 1) in chunks
        assert ("file-2", 0) in chunks
    
    def test_handle_node_failure(self, replication_manager):
        """Test handling node failure"""
        # Setup: Register chunks with proper replication
        for chunk_id in range(3):
            replication_manager.register_chunk("file-1", chunk_id, "node-1")
            replication_manager.register_chunk("file-1", chunk_id, "node-2")
            replication_manager.register_chunk("file-1", chunk_id, "node-3")
        
        # Simulate node-1 failure
        under_replicated = replication_manager.handle_node_failure("node-1")
        
        # All chunks should now have only 2 replicas (under-replicated)
        assert len(under_replicated) == 3
        
        for chunk_id in range(3):
            count = replication_manager.get_replication_count("file-1", chunk_id)
            assert count == 2  # Lost one replica
    
    def test_handle_catastrophic_failure(self, replication_manager):
        """Test handling failure when chunk has only 1 replica"""
        # Register chunk on only one node
        replication_manager.register_chunk("file-1", 0, "node-1")
        
        # Simulate failure
        under_replicated = replication_manager.handle_node_failure("node-1")
        
        # Chunk should be completely lost
        count = replication_manager.get_replication_count("file-1", 0)
        assert count == 0
        assert ("file-1", 0) in under_replicated


class TestStatistics:
    """Test replication statistics"""
    
    def test_statistics(self, replication_manager):
        """Test getting replication statistics"""
        # Register some chunks
        replication_manager.register_chunk("file-1", 0, "node-1")
        replication_manager.register_chunk("file-1", 0, "node-2")
        replication_manager.register_chunk("file-1", 0, "node-3")
        replication_manager.register_chunk("file-2", 0, "node-1")
        
        stats = replication_manager.get_statistics()
        
        assert stats["total_chunks"] == 2
        assert stats["total_replicas"] == 4
        assert stats["avg_replication_factor"] == 2.0
    
    def test_under_replicated_stats(self, replication_manager):
        """Test under-replication statistics"""
        # Create under-replicated chunk
        replication_manager.register_chunk("file-1", 0, "node-1")
        
        # Create properly replicated chunk
        replication_manager.register_chunk("file-2", 0, "node-1")
        replication_manager.register_chunk("file-2", 0, "node-2")
        replication_manager.register_chunk("file-2", 0, "node-3")
        
        stats = replication_manager.get_statistics()
        
        assert stats["under_replicated_chunks"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

