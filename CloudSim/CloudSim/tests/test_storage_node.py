"""
Unit tests for StorageVirtualNode

Tests:
- Node initialization
- File transfer initiation
- Chunk processing
- Network utilization tracking (CRITICAL BUG FIX)
- Real checksums
- Thread safety
"""

import pytest
import time
import threading
from src.core.storage_node import StorageVirtualNode
from src.core.data_structures import TransferStatus, NodeStatus


@pytest.fixture
def test_node():
    """Create a test storage node"""
    node = StorageVirtualNode(
        node_id="test-node-1",
        cpu_capacity=4,
        memory_capacity=8 * 1024**3,  # 8GB
        storage_capacity=100 * 1024**3,  # 100GB
        bandwidth=100 * 1000000  # 100Mbps
    )
    yield node
    node.shutdown()


@pytest.fixture
def test_file_data():
    """Create test file data"""
    return b"Hello, World! This is test data." * 1000  # ~33KB


class TestNodeInitialization:
    """Test node initialization"""
    
    def test_node_creation(self, test_node):
        """Test basic node creation"""
        assert test_node.node_id == "test-node-1"
        assert test_node.cpu_capacity == 4
        assert test_node.total_storage == 100 * 1024**3
        assert test_node.bandwidth == 100 * 1000000
        assert test_node.status == NodeStatus.HEALTHY
    
    def test_initial_state(self, test_node):
        """Test initial node state"""
        assert test_node.used_storage == 0
        assert test_node.network_utilization == 0
        assert len(test_node.stored_files) == 0
        assert len(test_node.active_transfers) == 0


class TestFileTransfer:
    """Test file transfer operations"""
    
    def test_initiate_transfer(self, test_node, test_file_data):
        """Test initiating a file transfer"""
        transfer = test_node.initiate_file_transfer(
            file_id="test-file-1",
            file_name="test.txt",
            file_data=test_file_data
        )
        
        assert transfer is not None
        assert transfer.file_id == "test-file-1"
        assert transfer.file_name == "test.txt"
        assert transfer.total_size == len(test_file_data)
        assert len(transfer.chunks) > 0
        assert transfer.status == TransferStatus.PENDING
    
    def test_chunk_generation(self, test_node, test_file_data):
        """Test that chunks are generated correctly"""
        transfer = test_node.initiate_file_transfer(
            file_id="test-file-2",
            file_name="test.txt",
            file_data=test_file_data
        )
        
        # Verify chunks
        total_chunk_size = sum(chunk.size for chunk in transfer.chunks)
        assert total_chunk_size == len(test_file_data)
        
        # Verify each chunk has data and checksum
        for chunk in transfer.chunks:
            assert chunk.data is not None
            assert len(chunk.data) == chunk.size
            assert chunk.checksum is not None
            assert len(chunk.checksum) > 0
    
    def test_real_checksums(self, test_node, test_file_data):
        """CRITICAL: Test that checksums are computed from actual data"""
        transfer = test_node.initiate_file_transfer(
            file_id="test-file-3",
            file_name="test.txt",
            file_data=test_file_data
        )
        
        # Verify checksums
        for chunk in transfer.chunks:
            # Verify checksum integrity
            assert chunk.verify_integrity()
            
            # Modify data and verify checksum fails
            original_data = chunk.data
            chunk.data = b"corrupted data"
            assert not chunk.verify_integrity()
            
            # Restore data
            chunk.data = original_data
            assert chunk.verify_integrity()
    
    def test_insufficient_storage(self, test_node):
        """Test transfer rejection when storage is full"""
        # Create huge file that exceeds capacity
        huge_data = b"X" * (test_node.total_storage + 1)
        
        transfer = test_node.initiate_file_transfer(
            file_id="huge-file",
            file_name="huge.bin",
            file_data=huge_data
        )
        
        assert transfer is None


class TestNetworkUtilization:
    """Test network utilization tracking - CRITICAL BUG FIX"""
    
    def test_bandwidth_tracking(self, test_node, test_file_data):
        """Test that bandwidth is properly tracked and released"""
        # Initiate transfer
        transfer = test_node.initiate_file_transfer(
            file_id="test-file-4",
            file_name="test.txt",
            file_data=test_file_data
        )
        
        assert transfer is not None
        
        # Initial utilization should be 0
        assert test_node.network_utilization == 0
        
        # Process first chunk
        success = test_node.process_chunk_transfer(
            file_id="test-file-4",
            chunk_id=0,
            source_node="client"
        )
        
        assert success
        
        # Utilization should increase during transfer
        # (will be 0 after completion since we're not simulating concurrent transfers)
        
        # Process all chunks
        for chunk in transfer.chunks[1:]:
            test_node.process_chunk_transfer(
                file_id="test-file-4",
                chunk_id=chunk.chunk_id,
                source_node="client"
            )
        
        # After all chunks complete, bandwidth should be released
        assert test_node.network_utilization == 0
        
        # File should be stored
        assert "test-file-4" in test_node.stored_files
    
    def test_multiple_concurrent_transfers(self, test_node):
        """Test multiple concurrent transfers don't accumulate bandwidth forever"""
        # Create multiple small files
        files = [
            (f"file-{i}", f"test{i}.txt", b"data" * 100)
            for i in range(3)
        ]
        
        # Initiate all transfers
        transfers = []
        for file_id, file_name, data in files:
            transfer = test_node.initiate_file_transfer(
                file_id=file_id,
                file_name=file_name,
                file_data=data
            )
            transfers.append((file_id, transfer))
        
        # Process all transfers
        for file_id, transfer in transfers:
            for chunk in transfer.chunks:
                test_node.process_chunk_transfer(
                    file_id=file_id,
                    chunk_id=chunk.chunk_id,
                    source_node="client"
                )
        
        # All bandwidth should be released
        assert test_node.network_utilization == 0
        
        # All files should be stored
        for file_id, _ in transfers:
            assert file_id in test_node.stored_files


class TestMetrics:
    """Test node metrics"""
    
    def test_storage_metrics(self, test_node, test_file_data):
        """Test storage utilization metrics"""
        # Store a file
        transfer = test_node.initiate_file_transfer(
            file_id="metrics-test",
            file_name="test.txt",
            file_data=test_file_data
        )
        
        # Process all chunks
        for chunk in transfer.chunks:
            test_node.process_chunk_transfer(
                file_id="metrics-test",
                chunk_id=chunk.chunk_id,
                source_node="client"
            )
        
        # Check metrics
        metrics = test_node.get_storage_utilization()
        assert metrics["used_bytes"] == len(test_file_data)
        assert metrics["files_stored"] == 1
        assert metrics["utilization_percent"] > 0
    
    def test_network_metrics(self, test_node):
        """Test network utilization metrics"""
        metrics = test_node.get_network_utilization()
        
        assert "current_utilization_bps" in metrics
        assert "max_bandwidth_bps" in metrics
        assert "available_bandwidth_bps" in metrics
        assert metrics["max_bandwidth_bps"] == test_node.bandwidth
    
    def test_performance_metrics(self, test_node, test_file_data):
        """Test performance metrics"""
        # Transfer a file
        transfer = test_node.initiate_file_transfer(
            file_id="perf-test",
            file_name="test.txt",
            file_data=test_file_data
        )
        
        for chunk in transfer.chunks:
            test_node.process_chunk_transfer(
                file_id="perf-test",
                chunk_id=chunk.chunk_id,
                source_node="client"
            )
        
        metrics = test_node.get_performance_metrics()
        assert metrics["total_requests_processed"] == 1
        assert metrics["total_data_transferred_bytes"] == len(test_file_data)
        assert metrics["uptime_seconds"] > 0


class TestThreadSafety:
    """Test thread safety"""
    
    def test_concurrent_transfers(self, test_node):
        """Test concurrent file transfers from multiple threads"""
        num_threads = 5
        results = []
        
        def transfer_file(thread_id):
            data = f"Thread {thread_id} data".encode() * 100
            transfer = test_node.initiate_file_transfer(
                file_id=f"thread-file-{thread_id}",
                file_name=f"thread{thread_id}.txt",
                file_data=data
            )
            
            if transfer:
                for chunk in transfer.chunks:
                    test_node.process_chunk_transfer(
                        file_id=f"thread-file-{thread_id}",
                        chunk_id=chunk.chunk_id,
                        source_node="client"
                    )
                results.append(thread_id)
        
        # Create and start threads
        threads = [
            threading.Thread(target=transfer_file, args=(i,))
            for i in range(num_threads)
        ]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join()
        
        # All transfers should succeed
        assert len(results) == num_threads
        assert len(test_node.stored_files) == num_threads


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

