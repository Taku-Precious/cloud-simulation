"""
Quick Test - Verify system works without pytest
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.storage_node import StorageVirtualNode
from src.core.storage_network import StorageVirtualNetwork
from src.core.data_structures import NodeStatus
import time

def test_basic_functionality():
    """Test basic system functionality"""
    print("=" * 80)
    print("QUICK TEST - CloudSim Distributed Storage System")
    print("=" * 80)
    
    # Test 1: Create nodes
    print("\n[TEST 1] Creating storage nodes...")
    try:
        node1 = StorageVirtualNode(
            node_id="test-node-1",
            cpu_capacity=4,
            memory_capacity=8 * 1024**3,
            storage_capacity=100 * 1024**3,
            bandwidth=100 * 1000000
        )
        node2 = StorageVirtualNode(
            node_id="test-node-2",
            cpu_capacity=4,
            memory_capacity=8 * 1024**3,
            storage_capacity=100 * 1024**3,
            bandwidth=100 * 1000000
        )
        print("✅ Nodes created successfully")
    except Exception as e:
        print(f"❌ Failed to create nodes: {e}")
        return False
    
    # Test 2: Create network
    print("\n[TEST 2] Creating storage network...")
    try:
        network = StorageVirtualNetwork()
        network.add_node(node1)
        network.add_node(node2)
        network.connect_nodes("test-node-1", "test-node-2", 100 * 1000000)
        network.start()
        time.sleep(0.5)  # Wait for heartbeats
        print("✅ Network created successfully")
    except Exception as e:
        print(f"❌ Failed to create network: {e}")
        return False
    
    # Test 3: Upload file with replication
    print("\n[TEST 3] Uploading file with 2x replication...")
    try:
        test_data = b"Hello, CloudSim!" * 1000
        file_id = network.initiate_file_transfer_with_replication(
            file_name="test.txt",
            file_data=test_data,
            replication_factor=2
        )
        
        if file_id:
            print(f"✅ File transfer initiated: {file_id}")
        else:
            print("❌ Failed to initiate transfer")
            return False
    except Exception as e:
        print(f"❌ Failed to upload file: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 4: Process transfer
    print("\n[TEST 4] Processing file transfer...")
    try:
        chunks_transferred, complete = network.process_file_transfer(
            file_id=file_id,
            chunks_per_step=10
        )
        print(f"✅ Transferred {chunks_transferred} chunks, Complete: {complete}")
    except Exception as e:
        print(f"❌ Failed to process transfer: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 5: Check network stats
    print("\n[TEST 5] Checking network statistics...")
    try:
        stats = network.get_network_stats()
        print(f"✅ Network Stats:")
        print(f"   Total Nodes: {stats['total_nodes']}")
        print(f"   Healthy Nodes: {stats['healthy_nodes']}")
        print(f"   Total Transfers: {stats['total_transfers']}")
    except Exception as e:
        print(f"❌ Failed to get stats: {e}")
        return False
    
    # Test 6: Check node metrics
    print("\n[TEST 6] Checking node metrics...")
    try:
        metrics = node1.get_metrics()
        print(f"✅ Node Metrics:")
        print(f"   Storage Used: {metrics.used_storage_bytes / 1024:.1f} KB")
        print(f"   Chunks Stored: {metrics.chunks_stored}")
        print(f"   Completed Transfers: {metrics.completed_transfers}")
    except Exception as e:
        print(f"❌ Failed to get metrics: {e}")
        return False
    
    # Test 7: Verify checksums
    print("\n[TEST 7] Verifying data integrity (checksums)...")
    try:
        # Check that chunks have real checksums
        for node in [node1, node2]:
            for file_transfer in node.stored_files.values():
                for chunk in file_transfer.chunks:
                    if chunk.verify_integrity():
                        print(f"✅ Chunk {chunk.chunk_id} checksum valid")
                    else:
                        print(f"❌ Chunk {chunk.chunk_id} checksum INVALID")
                        return False
    except Exception as e:
        print(f"❌ Failed to verify checksums: {e}")
        return False
    
    # Cleanup
    print("\n[CLEANUP] Shutting down...")
    try:
        network.stop()
        print("✅ Shutdown complete")
    except Exception as e:
        print(f"⚠️  Shutdown warning: {e}")
    
    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED - System is working correctly!")
    print("=" * 80)
    return True


if __name__ == "__main__":
    try:
        success = test_basic_functionality()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

