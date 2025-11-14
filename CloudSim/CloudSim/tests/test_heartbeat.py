"""
Unit tests for HeartbeatMonitor

Tests:
- Heartbeat reception and tracking
- Node failure detection
- Node recovery detection
- Callbacks
- Statistics
"""

import pytest
import time
from datetime import datetime, timedelta
from src.monitoring.heartbeat_monitor import HeartbeatMonitor
from src.core.data_structures import HeartbeatMessage, NodeStatus, NodeMetrics


@pytest.fixture
def heartbeat_monitor():
    """Create a test heartbeat monitor"""
    monitor = HeartbeatMonitor()
    yield monitor
    monitor.stop()


@pytest.fixture
def sample_heartbeat():
    """Create a sample heartbeat message"""
    metrics = NodeMetrics(
        node_id="test-node",
        total_storage_bytes=100 * 1024**3,
        used_storage_bytes=10 * 1024**3,
        available_storage_bytes=90 * 1024**3,
        storage_utilization_percent=10.0,
        total_bandwidth_bps=100 * 1000000,
        used_bandwidth_bps=0,
        available_bandwidth_bps=100 * 1000000,
        bandwidth_utilization_percent=0.0,
        active_transfers=0,
        completed_transfers=0,
        failed_transfers=0,
        total_data_transferred_bytes=0,
        chunks_stored=0,
        unique_files=0,
        replication_factor_avg=0.0,
        avg_transfer_speed_mbps=0.0,
        uptime_seconds=100.0
    )
    
    return HeartbeatMessage(
        node_id="test-node",
        status=NodeStatus.HEALTHY,
        metrics=metrics
    )


class TestHeartbeatReception:
    """Test heartbeat reception and tracking"""
    
    def test_receive_first_heartbeat(self, heartbeat_monitor, sample_heartbeat):
        """Test receiving first heartbeat from a node"""
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        assert "test-node" in heartbeat_monitor.healthy_nodes
        assert "test-node" in heartbeat_monitor.last_heartbeat
        assert heartbeat_monitor.is_node_healthy("test-node")
    
    def test_receive_multiple_heartbeats(self, heartbeat_monitor, sample_heartbeat):
        """Test receiving multiple heartbeats updates timestamp"""
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        first_time = heartbeat_monitor.last_heartbeat["test-node"]
        
        time.sleep(0.1)
        
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        second_time = heartbeat_monitor.last_heartbeat["test-node"]
        
        assert second_time > first_time
    
    def test_heartbeat_history(self, heartbeat_monitor, sample_heartbeat):
        """Test heartbeat history tracking"""
        # Send multiple heartbeats
        for _ in range(5):
            heartbeat_monitor.receive_heartbeat(sample_heartbeat)
            time.sleep(0.01)
        
        history = heartbeat_monitor.get_node_heartbeat_history("test-node", limit=10)
        assert len(history) == 5
    
    def test_multiple_nodes(self, heartbeat_monitor):
        """Test tracking multiple nodes"""
        for i in range(3):
            metrics = NodeMetrics(
                node_id=f"node-{i}",
                total_storage_bytes=100 * 1024**3,
                used_storage_bytes=0,
                available_storage_bytes=100 * 1024**3,
                storage_utilization_percent=0.0,
                total_bandwidth_bps=100 * 1000000,
                used_bandwidth_bps=0,
                available_bandwidth_bps=100 * 1000000,
                bandwidth_utilization_percent=0.0,
                active_transfers=0,
                completed_transfers=0,
                failed_transfers=0,
                total_data_transferred_bytes=0,
                chunks_stored=0,
                unique_files=0,
                replication_factor_avg=0.0,
                avg_transfer_speed_mbps=0.0,
                uptime_seconds=0.0
            )
            
            hb = HeartbeatMessage(
                node_id=f"node-{i}",
                status=NodeStatus.HEALTHY,
                metrics=metrics
            )
            heartbeat_monitor.receive_heartbeat(hb)
        
        assert len(heartbeat_monitor.healthy_nodes) == 3


class TestFailureDetection:
    """Test node failure detection"""
    
    def test_manual_failure_detection(self, heartbeat_monitor, sample_heartbeat):
        """Test manual failure detection by checking old heartbeat"""
        # Receive heartbeat
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        # Manually set old timestamp to simulate timeout
        old_time = datetime.now() - timedelta(seconds=100)
        heartbeat_monitor.last_heartbeat["test-node"] = old_time
        
        # Run check
        heartbeat_monitor._check_all_nodes()
        
        # Node should be marked as failed
        assert "test-node" in heartbeat_monitor.failed_nodes
        assert "test-node" not in heartbeat_monitor.healthy_nodes
        assert heartbeat_monitor.is_node_failed("test-node")
    
    def test_failure_callback(self, heartbeat_monitor, sample_heartbeat):
        """Test failure callback is triggered"""
        failed_nodes = []
        
        def on_failure(node_id):
            failed_nodes.append(node_id)
        
        heartbeat_monitor.register_failure_callback(on_failure)
        
        # Receive heartbeat
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        # Simulate timeout
        old_time = datetime.now() - timedelta(seconds=100)
        heartbeat_monitor.last_heartbeat["test-node"] = old_time
        
        # Check nodes
        heartbeat_monitor._check_all_nodes()
        
        # Callback should have been called
        assert "test-node" in failed_nodes
    
    def test_failure_statistics(self, heartbeat_monitor, sample_heartbeat):
        """Test failure statistics tracking"""
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        # Simulate failure
        old_time = datetime.now() - timedelta(seconds=100)
        heartbeat_monitor.last_heartbeat["test-node"] = old_time
        heartbeat_monitor._check_all_nodes()
        
        stats = heartbeat_monitor.get_statistics()
        assert stats["total_failures"] == 1
        assert stats["failed_nodes"] == 1


class TestRecoveryDetection:
    """Test node recovery detection"""
    
    def test_recovery_after_failure(self, heartbeat_monitor, sample_heartbeat):
        """Test detecting node recovery after failure"""
        # Initial heartbeat
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        # Simulate failure
        old_time = datetime.now() - timedelta(seconds=100)
        heartbeat_monitor.last_heartbeat["test-node"] = old_time
        heartbeat_monitor._check_all_nodes()
        
        assert "test-node" in heartbeat_monitor.failed_nodes
        
        # Node recovers - send new heartbeat
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        # Node should be healthy again
        assert "test-node" in heartbeat_monitor.healthy_nodes
        assert "test-node" not in heartbeat_monitor.failed_nodes
    
    def test_recovery_callback(self, heartbeat_monitor, sample_heartbeat):
        """Test recovery callback is triggered"""
        recovered_nodes = []
        
        def on_recovery(node_id):
            recovered_nodes.append(node_id)
        
        heartbeat_monitor.register_recovery_callback(on_recovery)
        
        # Initial heartbeat
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        # Simulate failure
        old_time = datetime.now() - timedelta(seconds=100)
        heartbeat_monitor.last_heartbeat["test-node"] = old_time
        heartbeat_monitor._check_all_nodes()
        
        # Recover
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        # Callback should have been called
        assert "test-node" in recovered_nodes
    
    def test_recovery_statistics(self, heartbeat_monitor, sample_heartbeat):
        """Test recovery statistics tracking"""
        # Fail and recover
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        old_time = datetime.now() - timedelta(seconds=100)
        heartbeat_monitor.last_heartbeat["test-node"] = old_time
        heartbeat_monitor._check_all_nodes()
        
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        stats = heartbeat_monitor.get_statistics()
        assert stats["total_recoveries"] == 1


class TestNodeStatus:
    """Test node status queries"""
    
    def test_get_node_status_healthy(self, heartbeat_monitor, sample_heartbeat):
        """Test getting status of healthy node"""
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        status = heartbeat_monitor.get_node_status("test-node")
        assert status == NodeStatus.HEALTHY
    
    def test_get_node_status_failed(self, heartbeat_monitor, sample_heartbeat):
        """Test getting status of failed node"""
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        # Simulate failure
        old_time = datetime.now() - timedelta(seconds=100)
        heartbeat_monitor.last_heartbeat["test-node"] = old_time
        heartbeat_monitor._check_all_nodes()
        
        status = heartbeat_monitor.get_node_status("test-node")
        assert status == NodeStatus.FAILED
    
    def test_get_node_status_offline(self, heartbeat_monitor):
        """Test getting status of unknown node"""
        status = heartbeat_monitor.get_node_status("unknown-node")
        assert status == NodeStatus.OFFLINE
    
    def test_get_healthy_nodes(self, heartbeat_monitor):
        """Test getting set of healthy nodes"""
        # Add multiple nodes
        for i in range(3):
            metrics = NodeMetrics(
                node_id=f"node-{i}",
                total_storage_bytes=100 * 1024**3,
                used_storage_bytes=0,
                available_storage_bytes=100 * 1024**3,
                storage_utilization_percent=0.0,
                total_bandwidth_bps=100 * 1000000,
                used_bandwidth_bps=0,
                available_bandwidth_bps=100 * 1000000,
                bandwidth_utilization_percent=0.0,
                active_transfers=0,
                completed_transfers=0,
                failed_transfers=0,
                total_data_transferred_bytes=0,
                chunks_stored=0,
                unique_files=0,
                replication_factor_avg=0.0,
                avg_transfer_speed_mbps=0.0,
                uptime_seconds=0.0
            )
            
            hb = HeartbeatMessage(
                node_id=f"node-{i}",
                status=NodeStatus.HEALTHY,
                metrics=metrics
            )
            heartbeat_monitor.receive_heartbeat(hb)
        
        healthy = heartbeat_monitor.get_healthy_nodes()
        assert len(healthy) == 3
        assert "node-0" in healthy
        assert "node-1" in healthy
        assert "node-2" in healthy


class TestMonitoringLoop:
    """Test background monitoring loop"""
    
    def test_start_stop_monitor(self, heartbeat_monitor):
        """Test starting and stopping monitor"""
        heartbeat_monitor.start()
        assert heartbeat_monitor.running
        
        heartbeat_monitor.stop()
        assert not heartbeat_monitor.running
    
    def test_automatic_failure_detection(self, heartbeat_monitor, sample_heartbeat):
        """Test automatic failure detection in background"""
        failed_nodes = []
        
        def on_failure(node_id):
            failed_nodes.append(node_id)
        
        heartbeat_monitor.register_failure_callback(on_failure)
        heartbeat_monitor.start()
        
        # Send heartbeat
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        # Simulate old heartbeat
        old_time = datetime.now() - timedelta(seconds=100)
        heartbeat_monitor.last_heartbeat["test-node"] = old_time
        
        # Wait for monitor to detect failure
        time.sleep(2)
        
        # Should be detected as failed
        assert "test-node" in failed_nodes or "test-node" in heartbeat_monitor.failed_nodes


class TestStatistics:
    """Test monitoring statistics"""
    
    def test_statistics(self, heartbeat_monitor, sample_heartbeat):
        """Test getting monitoring statistics"""
        heartbeat_monitor.receive_heartbeat(sample_heartbeat)
        
        stats = heartbeat_monitor.get_statistics()
        
        assert "uptime_seconds" in stats
        assert "total_nodes" in stats
        assert "healthy_nodes" in stats
        assert "failed_nodes" in stats
        assert stats["total_nodes"] == 1
        assert stats["healthy_nodes"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

