"""
Heartbeat Monitor
Monitors node health and detects failures
"""

import threading
import time
from typing import Dict, Set, Callable, Optional
from datetime import datetime, timedelta
from collections import defaultdict

from src.core.data_structures import HeartbeatMessage, NodeStatus
from src.utils.logger import get_logger
from src.utils.config_loader import get_config

logger = get_logger(__name__)


class HeartbeatMonitor:
    """
    Monitors heartbeats from storage nodes and detects failures
    
    Features:
    - Tracks last heartbeat from each node
    - Detects node failures (missed heartbeats)
    - Detects node recovery
    - Triggers callbacks on failure/recovery events
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize heartbeat monitor
        
        Args:
            config_path: Path to configuration file
        """
        self.config = get_config(config_path)
        
        # Heartbeat tracking
        self.last_heartbeat: Dict[str, datetime] = {}
        self.heartbeat_history: Dict[str, list] = defaultdict(list)
        
        # Node status tracking
        self.healthy_nodes: Set[str] = set()
        self.failed_nodes: Set[str] = set()
        self.recovering_nodes: Set[str] = set()
        
        # Callbacks
        self.on_node_failure: Optional[Callable] = None
        self.on_node_recovery: Optional[Callable] = None
        
        # Monitoring thread
        self.monitor_thread: Optional[threading.Thread] = None
        self.running = False
        
        # Statistics
        self.total_failures = 0
        self.total_recoveries = 0
        self.start_time = time.time()
        
        logger.info(
            f"HeartbeatMonitor initialized: "
            f"interval={self.config.monitoring.heartbeat_interval}s, "
            f"timeout={self.config.monitoring.failure_timeout}s"
        )
    
    def start(self):
        """Start heartbeat monitoring in background thread"""
        if self.running:
            logger.warning("HeartbeatMonitor already running")
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info("HeartbeatMonitor started")
    
    def stop(self):
        """Stop heartbeat monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        logger.info("HeartbeatMonitor stopped")
    
    def _monitor_loop(self):
        """Background thread that checks heartbeats"""
        check_interval = self.config.monitoring.recovery_check_interval
        
        while self.running:
            try:
                self._check_all_nodes()
            except Exception as e:
                logger.error(f"Error in heartbeat monitor loop: {e}", exc_info=True)
            
            time.sleep(check_interval)
    
    def _check_all_nodes(self):
        """Check all nodes for missed heartbeats"""
        now = datetime.now()
        timeout = timedelta(seconds=self.config.monitoring.failure_timeout)
        
        # Check each node
        for node_id, last_hb in list(self.last_heartbeat.items()):
            time_since_heartbeat = now - last_hb
            
            # Node has missed heartbeat timeout
            if time_since_heartbeat > timeout:
                if node_id not in self.failed_nodes:
                    self._mark_node_failed(node_id, time_since_heartbeat.total_seconds())
            
            # Node is healthy
            else:
                if node_id in self.failed_nodes:
                    self._mark_node_recovered(node_id)
                elif node_id not in self.healthy_nodes:
                    self.healthy_nodes.add(node_id)
    
    def _mark_node_failed(self, node_id: str, time_since_heartbeat: float):
        """Mark a node as failed"""
        logger.warning(
            f"⚠️  NODE FAILURE DETECTED: {node_id} "
            f"(no heartbeat for {time_since_heartbeat:.1f}s)"
        )
        
        # Update status
        self.healthy_nodes.discard(node_id)
        self.failed_nodes.add(node_id)
        self.total_failures += 1
        
        # Trigger callback
        if self.on_node_failure:
            try:
                self.on_node_failure(node_id)
            except Exception as e:
                logger.error(f"Error in node failure callback: {e}", exc_info=True)
    
    def _mark_node_recovered(self, node_id: str):
        """Mark a node as recovered"""
        logger.info(f"✅ NODE RECOVERED: {node_id}")
        
        # Update status
        self.failed_nodes.discard(node_id)
        self.healthy_nodes.add(node_id)
        self.total_recoveries += 1
        
        # Trigger callback
        if self.on_node_recovery:
            try:
                self.on_node_recovery(node_id)
            except Exception as e:
                logger.error(f"Error in node recovery callback: {e}", exc_info=True)
    
    def receive_heartbeat(self, heartbeat: HeartbeatMessage):
        """
        Receive and process a heartbeat from a node
        
        Args:
            heartbeat: HeartbeatMessage from node
        """
        node_id = heartbeat.node_id
        now = datetime.now()
        
        # Update last heartbeat time
        self.last_heartbeat[node_id] = now
        
        # Store in history (keep last 100)
        self.heartbeat_history[node_id].append({
            'timestamp': now,
            'status': heartbeat.status,
            'metrics': heartbeat.metrics
        })
        if len(self.heartbeat_history[node_id]) > 100:
            self.heartbeat_history[node_id].pop(0)
        
        # Check if this is a recovery from failure
        if node_id in self.failed_nodes:
            self._mark_node_recovered(node_id)
        elif node_id not in self.healthy_nodes:
            self.healthy_nodes.add(node_id)
            logger.info(f"New node registered: {node_id}")
        
        logger.debug(
            f"Heartbeat received from {node_id} "
            f"(status={heartbeat.status.name})"
        )
    
    def get_node_status(self, node_id: str) -> NodeStatus:
        """Get current status of a node"""
        if node_id in self.failed_nodes:
            return NodeStatus.FAILED
        elif node_id in self.healthy_nodes:
            return NodeStatus.HEALTHY
        else:
            return NodeStatus.OFFLINE
    
    def is_node_healthy(self, node_id: str) -> bool:
        """Check if a node is healthy"""
        return node_id in self.healthy_nodes
    
    def is_node_failed(self, node_id: str) -> bool:
        """Check if a node has failed"""
        return node_id in self.failed_nodes
    
    def get_healthy_nodes(self) -> Set[str]:
        """Get set of healthy node IDs"""
        return self.healthy_nodes.copy()
    
    def get_failed_nodes(self) -> Set[str]:
        """Get set of failed node IDs"""
        return self.failed_nodes.copy()
    
    def get_statistics(self) -> Dict:
        """Get monitoring statistics"""
        uptime = time.time() - self.start_time
        
        return {
            "uptime_seconds": uptime,
            "total_nodes": len(self.last_heartbeat),
            "healthy_nodes": len(self.healthy_nodes),
            "failed_nodes": len(self.failed_nodes),
            "total_failures": self.total_failures,
            "total_recoveries": self.total_recoveries,
            "failure_rate": self.total_failures / uptime if uptime > 0 else 0,
            "recovery_rate": self.total_recoveries / uptime if uptime > 0 else 0
        }
    
    def get_node_heartbeat_history(self, node_id: str, limit: int = 10) -> list:
        """
        Get recent heartbeat history for a node
        
        Args:
            node_id: Node ID
            limit: Maximum number of entries to return
        
        Returns:
            List of recent heartbeat records
        """
        history = self.heartbeat_history.get(node_id, [])
        return history[-limit:]
    
    def register_failure_callback(self, callback: Callable):
        """
        Register callback for node failure events
        
        Args:
            callback: Function to call when node fails (receives node_id)
        """
        self.on_node_failure = callback
        logger.info("Node failure callback registered")
    
    def register_recovery_callback(self, callback: Callable):
        """
        Register callback for node recovery events
        
        Args:
            callback: Function to call when node recovers (receives node_id)
        """
        self.on_node_recovery = callback
        logger.info("Node recovery callback registered")
    
    def __repr__(self) -> str:
        """String representation"""
        return (
            f"HeartbeatMonitor("
            f"healthy={len(self.healthy_nodes)}, "
            f"failed={len(self.failed_nodes)}, "
            f"total_failures={self.total_failures})"
        )

