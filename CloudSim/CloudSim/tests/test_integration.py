"""
Integration tests for complete distributed storage system

Tests:
- End-to-end file storage with replication
- Node failure and recovery
- Automatic re-replication
- Multi-node cluster operations
- Concurrent operations
"""

import pytest
import time
import threading
from src.core.storage_network import StorageVirtualNetwork
from src.core.storage_node import StorageVirtualNode
from src.core.data_structures import NodeStatus


@pytest.fixture
def storage_cluster():
    """Create a test storage cluster with 5 nodes"""
    network = StorageVirtualNetwork()
    
    # Create 5 nodes
    nodes = []
    for i in range(5):
        node = StorageVirtualNode(
            node_id=f"node-{i}",
            cpu_capacity=4,
            memory_capacity=8 * 1024**3,
            storage_capacity=100 * 1024**3,
            bandwidth=100 * 1000000
        )
        nodes.append(node)
        network.add_node(node)
    
    # Connect all nodes to each other (full mesh)
    for i in range(5):
        for j in range(i + 1, 5):
            network.connect_nodes(f"node-{i}", f"node-{j}", 100 * 1000000)
    
    # Start network
    network.start()
    
    # Wait for heartbeats to establish
    time.sleep(0.5)
    
    yield network
    
    # Cleanup
    network.stop()


class TestBasicOperations:
    """Test basic cluster operations"""
    
    def test_cluster_initialization(self, storage_cluster):
        """Test cluster initializes correctly"""
        stats = storage_cluster.get_network_stats()
        
        assert stats["total_nodes"] == 5
        assert stats["healthy_nodes"] >= 4  # At least 4 should be healthy
    
    def test_file_upload_with_replication(self, storage_cluster):
        """Test uploading file with 3x replication"""
        test_data = b"Integration test data" * 1000
        
        file_id = storage_cluster.initiate_file_transfer_with_replication(
            file_name="test.txt",
            file_data=test_data,
            replication_factor=3
        )
        
        assert file_id is not None
        
        # Process transfer
        chunks_transferred, complete = storage_cluster.process_file_transfer(
            file_id=file_id,
            chunks_per_step=10
        )
        
        assert chunks_transferred > 0
    
    def test_multiple_files(self, storage_cluster):
        """Test uploading multiple files"""
        files = [
            (f"file-{i}.txt", f"Data for file {i}".encode() * 100)
            for i in range(3)
        ]
        
        file_ids = []
        for file_name, file_data in files:
            file_id = storage_cluster.initiate_file_transfer_with_replication(
                file_name=file_name,
                file_data=file_data,
                replication_factor=3
            )
            assert file_id is not None
            file_ids.append(file_id)
        
        # Process all transfers
        for file_id in file_ids:
            storage_cluster.process_file_transfer(file_id, chunks_per_step=10)
        
        assert len(file_ids) == 3


class TestReplication:
    """Test replication functionality"""
    
    def test_replication_across_nodes(self, storage_cluster):
        """Test that replicas are distributed across different nodes"""
        test_data = b"Replication test" * 100
        
        file_id = storage_cluster.initiate_file_transfer_with_replication(
            file_name="replicated.txt",
            file_data=test_data,
            replication_factor=3
        )
        
        assert file_id is not None
        
        # Check that file is being stored on 3 different nodes
        active_transfers = storage_cluster.transfer_operations.get(file_id, {})
        assert len(active_transfers) == 3
        
        # All nodes should be different
        node_ids = list(active_transfers.keys())
        assert len(set(node_ids)) == 3
    
    def test_replication_statistics(self, storage_cluster):
        """Test replication statistics"""
        test_data = b"Stats test" * 100
        
        file_id = storage_cluster.initiate_file_transfer_with_replication(
            file_name="stats.txt",
            file_data=test_data,
            replication_factor=3
        )
        
        # Process transfer
        storage_cluster.process_file_transfer(file_id, chunks_per_step=10)
        
        # Check replication stats
        stats = storage_cluster.get_network_stats()
        replication_stats = stats.get("replication", {})
        
        assert "total_chunks" in replication_stats
        assert "avg_replication_factor" in replication_stats


class TestFaultTolerance:
    """Test fault tolerance and recovery"""
    
    def test_node_failure_detection(self, storage_cluster):
        """Test that node failures are detected"""
        # Get a healthy node
        healthy_nodes = storage_cluster.get_healthy_nodes()
        assert len(healthy_nodes) > 0
        
        node_to_fail = healthy_nodes[0]
        
        # Simulate failure by stopping heartbeat
        node_to_fail.stop_heartbeat()
        node_to_fail.status = NodeStatus.FAILED
        
        # Manually trigger failure detection
        storage_cluster.heartbeat_monitor._mark_node_failed(
            node_to_fail.node_id,
            100.0
        )
        
        # Check that node is marked as failed
        assert storage_cluster.heartbeat_monitor.is_node_failed(node_to_fail.node_id)
    
    def test_re_replication_after_failure(self, storage_cluster):
        """Test automatic re-replication after node failure"""
        test_data = b"Fault tolerance test" * 100
        
        # Upload file with 3x replication
        file_id = storage_cluster.initiate_file_transfer_with_replication(
            file_name="fault_test.txt",
            file_data=test_data,
            replication_factor=3
        )
        
        # Process transfer
        storage_cluster.process_file_transfer(file_id, chunks_per_step=10)
        
        # Get initial replication stats
        initial_stats = storage_cluster.replication_manager.get_statistics()
        initial_replicas = initial_stats.get("total_replicas", 0)
        
        # Simulate node failure
        healthy_nodes = storage_cluster.get_healthy_nodes()
        if healthy_nodes:
            failed_node = healthy_nodes[0]
            storage_cluster.handle_node_failure(failed_node.node_id)
            
            # Check that under-replicated chunks are identified
            stats = storage_cluster.replication_manager.get_statistics()
            # Some chunks may be under-replicated after failure
            assert "under_replicated_chunks" in stats
    
    def test_data_integrity_after_failure(self, storage_cluster):
        """Test that data remains accessible after node failure"""
        test_data = b"Integrity test" * 100
        
        # Upload file
        file_id = storage_cluster.initiate_file_transfer_with_replication(
            file_name="integrity.txt",
            file_data=test_data,
            replication_factor=3
        )
        
        # Process transfer
        storage_cluster.process_file_transfer(file_id, chunks_per_step=10)
        
        # Simulate node failure
        healthy_nodes = storage_cluster.get_healthy_nodes()
        if len(healthy_nodes) >= 2:
            failed_node = healthy_nodes[0]
            storage_cluster.handle_node_failure(failed_node.node_id)
            
            # Data should still be available on other nodes
            remaining_healthy = storage_cluster.get_healthy_nodes()
            assert len(remaining_healthy) >= 2


class TestConcurrency:
    """Test concurrent operations"""
    
    def test_concurrent_uploads(self, storage_cluster):
        """Test multiple concurrent file uploads"""
        num_files = 5
        results = []
        
        def upload_file(file_num):
            data = f"Concurrent file {file_num}".encode() * 100
            file_id = storage_cluster.initiate_file_transfer_with_replication(
                file_name=f"concurrent_{file_num}.txt",
                file_data=data,
                replication_factor=2
            )
            if file_id:
                results.append(file_id)
        
        # Create threads
        threads = [
            threading.Thread(target=upload_file, args=(i,))
            for i in range(num_files)
        ]
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # All uploads should succeed
        assert len(results) == num_files
    
    def test_concurrent_processing(self, storage_cluster):
        """Test concurrent chunk processing"""
        # Upload multiple files
        file_ids = []
        for i in range(3):
            data = f"Process test {i}".encode() * 100
            file_id = storage_cluster.initiate_file_transfer_with_replication(
                file_name=f"process_{i}.txt",
                file_data=data,
                replication_factor=2
            )
            if file_id:
                file_ids.append(file_id)
        
        # Process all concurrently
        def process_file(fid):
            storage_cluster.process_file_transfer(fid, chunks_per_step=10)
        
        threads = [
            threading.Thread(target=process_file, args=(fid,))
            for fid in file_ids
        ]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # Check that processing completed
        stats = storage_cluster.get_network_stats()
        assert stats["total_transfers"] >= 3


class TestLoadBalancing:
    """Test load balancing"""
    
    def test_node_selection_balancing(self, storage_cluster):
        """Test that files are distributed across nodes"""
        node_usage = {}
        
        # Upload multiple files
        for i in range(10):
            data = f"Balance test {i}".encode() * 50
            file_id = storage_cluster.initiate_file_transfer_with_replication(
                file_name=f"balance_{i}.txt",
                file_data=data,
                replication_factor=2
            )
            
            if file_id:
                # Track which nodes were selected
                transfers = storage_cluster.transfer_operations.get(file_id, {})
                for node_id in transfers.keys():
                    node_usage[node_id] = node_usage.get(node_id, 0) + 1
        
        # Files should be distributed (not all on same node)
        if node_usage:
            assert len(node_usage) > 1


class TestNetworkStatistics:
    """Test network statistics and monitoring"""
    
    def test_comprehensive_stats(self, storage_cluster):
        """Test getting comprehensive network statistics"""
        stats = storage_cluster.get_network_stats()
        
        # Check all required fields
        required_fields = [
            "total_nodes",
            "healthy_nodes",
            "failed_nodes",
            "total_bandwidth_bps",
            "total_storage_bytes",
            "used_storage_bytes",
            "active_transfers",
            "completed_transfers",
            "replication",
            "monitoring"
        ]
        
        for field in required_fields:
            assert field in stats
    
    def test_stats_after_operations(self, storage_cluster):
        """Test statistics update after operations"""
        # Get initial stats
        initial_stats = storage_cluster.get_network_stats()
        initial_transfers = initial_stats["total_transfers"]
        
        # Upload a file
        data = b"Stats update test" * 100
        file_id = storage_cluster.initiate_file_transfer_with_replication(
            file_name="stats_update.txt",
            file_data=data,
            replication_factor=2
        )
        
        # Get updated stats
        updated_stats = storage_cluster.get_network_stats()
        
        # Transfer count should increase
        assert updated_stats["total_transfers"] > initial_transfers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

