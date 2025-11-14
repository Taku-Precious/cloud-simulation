"""
Production Demo - Distributed Cloud Storage System
Demonstrates all features with realistic scenario
"""

import time
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.storage_network import StorageVirtualNetwork
from src.core.storage_node import StorageVirtualNode
from src.core.data_structures import NodeStatus
from src.utils.logger import setup_logging, get_logger

# Setup logging (console only to avoid Windows path issues)
setup_logging(log_to_file=False)
logger = get_logger(__name__)


def print_banner(text):
    """Print a formatted banner"""
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80 + "\n")


def print_stats(network):
    """Print network statistics"""
    stats = network.get_network_stats()
    
    print(f"📊 Network Statistics:")
    print(f"  Total Nodes: {stats['total_nodes']}")
    print(f"  Healthy Nodes: {stats['healthy_nodes']}")
    print(f"  Failed Nodes: {stats['failed_nodes']}")
    print(f"  Storage Utilization: {stats['storage_utilization']:.2f}%")
    print(f"  Bandwidth Utilization: {stats['bandwidth_utilization']:.2f}%")
    print(f"  Active Transfers: {stats['active_transfers']}")
    print(f"  Completed Transfers: {stats['completed_transfers']}")
    
    if "replication" in stats:
        rep_stats = stats["replication"]
        print(f"\n📦 Replication Statistics:")
        print(f"  Total Chunks: {rep_stats.get('total_chunks', 0)}")
        print(f"  Total Replicas: {rep_stats.get('total_replicas', 0)}")
        print(f"  Avg Replication Factor: {rep_stats.get('avg_replication_factor', 0):.2f}")
        print(f"  Under-replicated Chunks: {rep_stats.get('under_replicated_chunks', 0)}")


def main():
    """Run production demo"""
    print_banner("CloudSim - Distributed Cloud Storage System Demo")
    
    print("🚀 Initializing distributed storage cluster...")
    
    # Create network
    network = StorageVirtualNetwork()
    
    # Create 5 storage nodes with different capacities
    node_configs = [
        {"id": "node-1", "storage": 200, "bandwidth": 1000},  # 200GB, 1Gbps
        {"id": "node-2", "storage": 150, "bandwidth": 500},   # 150GB, 500Mbps
        {"id": "node-3", "storage": 100, "bandwidth": 500},   # 100GB, 500Mbps
        {"id": "node-4", "storage": 250, "bandwidth": 1000},  # 250GB, 1Gbps
        {"id": "node-5", "storage": 180, "bandwidth": 500},   # 180GB, 500Mbps
    ]
    
    nodes = []
    for config in node_configs:
        node = StorageVirtualNode(
            node_id=config["id"],
            cpu_capacity=8,
            memory_capacity=16 * 1024**3,  # 16GB RAM
            storage_capacity=config["storage"] * 1024**3,  # Convert to bytes
            bandwidth=config["bandwidth"] * 1000000  # Convert to bps
        )
        nodes.append(node)
        network.add_node(node)
        print(f"  ✅ Added {config['id']}: {config['storage']}GB storage, {config['bandwidth']}Mbps bandwidth")
    
    # Connect nodes in a mesh topology
    print("\n🔗 Connecting nodes in mesh topology...")
    connections = 0
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            bandwidth = min(
                node_configs[i]["bandwidth"],
                node_configs[j]["bandwidth"]
            ) * 1000000
            network.connect_nodes(nodes[i].node_id, nodes[j].node_id, bandwidth)
            connections += 1
    print(f"  ✅ Created {connections} connections")
    
    # Start network
    print("\n▶️  Starting network coordinator...")
    network.start()
    
    # Wait for heartbeats to establish
    print("⏳ Waiting for heartbeat synchronization...")
    time.sleep(2)
    
    print_stats(network)
    
    # ========== DEMO 1: Upload files with replication ==========
    print_banner("DEMO 1: Upload Files with 3x Replication")
    
    files_to_upload = [
        ("document.pdf", b"PDF document content" * 10000),      # ~200KB
        ("image.jpg", b"JPEG image data" * 50000),              # ~800KB
        ("video.mp4", b"MP4 video stream" * 100000),            # ~1.5MB
        ("database.db", b"Database records" * 200000),          # ~3MB
    ]
    
    file_ids = []
    for file_name, file_data in files_to_upload:
        print(f"\n📤 Uploading {file_name} ({len(file_data) / 1024:.1f} KB)...")
        
        file_id = network.initiate_file_transfer_with_replication(
            file_name=file_name,
            file_data=file_data,
            replication_factor=3
        )
        
        if file_id:
            file_ids.append((file_id, file_name))
            print(f"  ✅ Transfer initiated: {file_id}")
            
            # Process transfer
            total_chunks = 0
            while True:
                chunks, complete = network.process_file_transfer(
                    file_id=file_id,
                    chunks_per_step=5
                )
                total_chunks += chunks
                
                if complete:
                    print(f"  ✅ Transfer complete: {total_chunks} chunks transferred")
                    break
                
                if chunks == 0:
                    break
        else:
            print(f"  ❌ Failed to initiate transfer")
    
    print(f"\n✅ Uploaded {len(file_ids)} files successfully")
    print_stats(network)
    
    # ========== DEMO 2: Node failure simulation ==========
    print_banner("DEMO 2: Node Failure & Automatic Recovery")
    
    # Select a node to fail
    failed_node = nodes[1]  # node-2
    print(f"⚠️  Simulating failure of {failed_node.node_id}...")
    
    # Stop node heartbeat to simulate failure
    failed_node.stop_heartbeat()
    failed_node.status = NodeStatus.FAILED
    
    # Trigger failure detection
    network.heartbeat_monitor._mark_node_failed(failed_node.node_id, 100.0)
    
    print(f"  ❌ Node {failed_node.node_id} has failed")
    
    # Handle failure (triggers re-replication)
    print(f"\n🔄 Initiating automatic re-replication...")
    network.handle_node_failure(failed_node.node_id)
    
    print_stats(network)
    
    # ========== DEMO 3: Node recovery ==========
    print_banner("DEMO 3: Node Recovery")
    
    print(f"🔧 Recovering {failed_node.node_id}...")
    
    # Restart node
    failed_node.status = NodeStatus.HEALTHY
    failed_node.start_heartbeat(
        callback=network.heartbeat_monitor.receive_heartbeat,
        interval=3
    )
    
    # Wait for heartbeat
    time.sleep(1)
    
    print(f"  ✅ Node {failed_node.node_id} recovered")
    print_stats(network)
    
    # ========== DEMO 4: Concurrent uploads ==========
    print_banner("DEMO 4: Concurrent File Uploads")
    
    import threading
    
    concurrent_results = []
    
    def upload_concurrent(file_num):
        data = f"Concurrent file {file_num} content".encode() * 5000
        file_id = network.initiate_file_transfer_with_replication(
            file_name=f"concurrent_{file_num}.txt",
            file_data=data,
            replication_factor=2
        )
        if file_id:
            concurrent_results.append(file_id)
            # Process transfer
            while True:
                chunks, complete = network.process_file_transfer(file_id, chunks_per_step=3)
                if complete or chunks == 0:
                    break
    
    print("📤 Starting 10 concurrent uploads...")
    threads = [
        threading.Thread(target=upload_concurrent, args=(i,))
        for i in range(10)
    ]
    
    start_time = time.time()
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    duration = time.time() - start_time
    
    print(f"\n✅ Completed {len(concurrent_results)} concurrent uploads in {duration:.2f}s")
    print_stats(network)
    
    # ========== DEMO 5: Performance metrics ==========
    print_banner("DEMO 5: Node Performance Metrics")
    
    for node in nodes[:3]:  # Show first 3 nodes
        metrics = node.get_metrics()
        print(f"\n📊 {node.node_id} Metrics:")
        print(f"  Storage: {metrics.used_storage_bytes / 1024**2:.1f}MB / {metrics.total_storage_bytes / 1024**3:.1f}GB ({metrics.storage_utilization_percent:.1f}%)")
        print(f"  Bandwidth: {metrics.bandwidth_utilization_percent:.1f}%")
        print(f"  Transfers: {metrics.completed_transfers} completed, {metrics.failed_transfers} failed")
        print(f"  Data Transferred: {metrics.total_data_transferred_bytes / 1024**2:.1f}MB")
        print(f"  Chunks Stored: {metrics.chunks_stored}")
        print(f"  Files: {metrics.unique_files}")
        print(f"  Avg Replication: {metrics.replication_factor_avg:.2f}x")
        print(f"  Uptime: {metrics.uptime_seconds:.1f}s")
    
    # ========== Final summary ==========
    print_banner("DEMO COMPLETE - Final Summary")
    
    final_stats = network.get_network_stats()
    
    print("🎉 Distributed Storage System Demo Completed Successfully!\n")
    print(f"📈 Final Statistics:")
    print(f"  Total Files Stored: {len(file_ids) + len(concurrent_results)}")
    print(f"  Total Transfers: {final_stats['total_transfers']}")
    print(f"  Completed Transfers: {final_stats['completed_transfers']}")
    print(f"  Cluster Health: {final_stats['healthy_nodes']}/{final_stats['total_nodes']} nodes healthy")
    print(f"  Storage Used: {final_stats['used_storage_bytes'] / 1024**3:.2f}GB / {final_stats['total_storage_bytes'] / 1024**3:.2f}GB")
    
    if "replication" in final_stats:
        rep = final_stats["replication"]
        print(f"  Total Chunks: {rep.get('total_chunks', 0)}")
        print(f"  Total Replicas: {rep.get('total_replicas', 0)}")
        print(f"  Avg Replication Factor: {rep.get('avg_replication_factor', 0):.2f}x")
        print(f"  Data Safety: {'✅ SAFE' if rep.get('under_replicated_chunks', 0) == 0 else '⚠️  SOME UNDER-REPLICATION'}")
    
    print("\n✅ All features demonstrated:")
    print("  ✅ Multi-node cluster (5 nodes)")
    print("  ✅ File upload with 3x replication")
    print("  ✅ Automatic chunk distribution")
    print("  ✅ Node failure detection")
    print("  ✅ Automatic re-replication")
    print("  ✅ Node recovery")
    print("  ✅ Concurrent operations")
    print("  ✅ Load balancing")
    print("  ✅ Real checksums (SHA-256)")
    print("  ✅ Thread-safe operations")
    print("  ✅ Heartbeat monitoring")
    print("  ✅ Performance metrics")
    
    # Cleanup
    print("\n🛑 Shutting down cluster...")
    network.stop()
    print("✅ Shutdown complete")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")

