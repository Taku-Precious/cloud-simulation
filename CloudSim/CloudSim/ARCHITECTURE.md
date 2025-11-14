# CloudSim Architecture Documentation

## System Architecture Overview

CloudSim implements a **Master-Slave distributed architecture** similar to HDFS (Hadoop Distributed File System) and Google File System (GFS).

## Core Components

### 1. StorageVirtualNetwork (Master/Coordinator)

**Role:** Central coordinator managing the entire distributed storage cluster

**Responsibilities:**
- Node registry and health monitoring
- File transfer orchestration
- Replica placement decisions
- Failure detection and recovery
- Load balancing
- Network statistics aggregation

**Key Methods:**
```python
add_node(node)                              # Register storage node
initiate_file_transfer_with_replication()   # Start file upload with replication
process_file_transfer()                     # Process chunk transfers
handle_node_failure()                       # Handle node failures
get_network_stats()                         # Get cluster statistics
```

**Thread Safety:** Uses RLock for all critical operations

### 2. StorageVirtualNode (Worker/Slave)

**Role:** Individual storage node storing data chunks

**Responsibilities:**
- Store file chunks with real checksums
- Process chunk transfers with bandwidth tracking
- Send heartbeats to coordinator
- Maintain storage and network metrics
- Verify data integrity

**Key Methods:**
```python
initiate_file_transfer()      # Start receiving a file
process_chunk_transfer()      # Process individual chunk (FIXED: bandwidth bug)
get_metrics()                 # Get node performance metrics
start_heartbeat()             # Start sending heartbeats
```

**Thread Safety:** 
- `transfer_lock` (RLock) - For transfer operations
- `storage_lock` (Lock) - For storage updates
- `bandwidth_lock` (Lock) - For bandwidth tracking

### 3. ReplicationManager

**Role:** Manages data replication across nodes

**Responsibilities:**
- Track chunk locations across nodes
- Select optimal nodes for replica placement
- Detect under-replicated chunks
- Trigger re-replication on failures
- Maintain replication statistics

**Placement Strategies:**
- **Random:** Random node selection
- **Least Loaded:** Select nodes with most available storage
- **Diverse:** Maximize distribution across nodes (default)

**Key Data Structures:**
```python
chunk_locations: Dict[str, Set[str]]  # chunk_key -> set of node_ids
```

### 4. HeartbeatMonitor

**Role:** Monitor node health and detect failures

**Responsibilities:**
- Receive and track heartbeats from nodes
- Detect node failures (missed heartbeats)
- Detect node recovery
- Trigger callbacks on failure/recovery events
- Maintain node status (HEALTHY, FAILED, OFFLINE)

**Configuration:**
- Heartbeat interval: 3 seconds (default)
- Failure timeout: 30 seconds (default)
- Recovery check interval: 5 seconds (default)

**Background Thread:** Continuously monitors heartbeat timestamps

## Data Flow

### File Upload Flow

```
1. Client → StorageVirtualNetwork.initiate_file_transfer_with_replication()
   ├─ Generate unique file_id
   ├─ Select N target nodes (replication_factor)
   └─ For each target node:
      └─ StorageVirtualNode.initiate_file_transfer()
         ├─ Check storage capacity
         ├─ Generate chunks with REAL checksums
         └─ Create FileTransfer object

2. Client → StorageVirtualNetwork.process_file_transfer()
   └─ For each node:
      └─ StorageVirtualNode.process_chunk_transfer()
         ├─ Verify checksum (if enabled)
         ├─ Simulate network transfer
         ├─ Track bandwidth usage (FIXED)
         ├─ Store chunk
         └─ Release bandwidth on completion

3. ReplicationManager.register_chunk()
   └─ Track chunk location for each replica
```

### Node Failure Flow

```
1. HeartbeatMonitor detects missed heartbeat
   └─ _mark_node_failed()
      ├─ Update node status
      ├─ Trigger failure callback
      └─ Update statistics

2. StorageVirtualNetwork.handle_node_failure()
   └─ ReplicationManager.handle_node_failure()
      ├─ Find all chunks on failed node
      ├─ Unregister chunks from failed node
      └─ Identify under-replicated chunks

3. For each under-replicated chunk:
   └─ StorageVirtualNetwork._re_replicate_chunk()
      ├─ Get chunk from surviving replica
      ├─ Select new target nodes
      ├─ Transfer chunk to new nodes
      └─ Register new replicas
```

## Data Structures

### FileChunk
```python
@dataclass
class FileChunk:
    chunk_id: int
    size: int
    data: bytes                    # ADDED: Actual chunk data
    checksum: str                  # Real SHA-256 checksum
    stored_nodes: Set[str]         # Multiple nodes for replication
    status: TransferStatus
```

### FileTransfer
```python
@dataclass
class FileTransfer:
    file_id: str
    file_name: str
    total_size: int
    chunks: List[FileChunk]
    status: TransferStatus
    source_node: Optional[str]
    target_nodes: Set[str]
    replication_factor: int
```

### NodeMetrics
```python
@dataclass
class NodeMetrics:
    node_id: str
    total_storage_bytes: int
    used_storage_bytes: int
    storage_utilization_percent: float
    total_bandwidth_bps: int
    used_bandwidth_bps: int
    bandwidth_utilization_percent: float
    active_transfers: int
    completed_transfers: int
    chunks_stored: int
    replication_factor_avg: float
    uptime_seconds: float
```

## Critical Bug Fixes

### 1. Network Utilization Bug

**Original Code (BROKEN):**
```python
self.network_utilization += available_bandwidth * 0.8  # BUG: Never decreases!
```

**Fixed Code:**
```python
# Track bandwidth per transfer
transfer_key = f"{file_id}_{chunk_id}"
bandwidth_used = available_bandwidth * 0.8

with self.bandwidth_lock:
    self.active_bandwidth_usage[transfer_key] = bandwidth_used
    self.network_utilization = sum(self.active_bandwidth_usage.values())

# On completion, release bandwidth
with self.bandwidth_lock:
    del self.active_bandwidth_usage[transfer_key]
    self.network_utilization = sum(self.active_bandwidth_usage.values())
```

### 2. Fake Checksums

**Original Code (BROKEN):**
```python
fake_checksum = hashlib.md5(f"{file_id}-{i}".encode()).hexdigest()
# Checksum from metadata, not data!
```

**Fixed Code:**
```python
chunk_data = file_data[start:end]
real_checksum = hashlib.sha256(chunk_data).hexdigest()
chunk = FileChunk(
    chunk_id=i,
    size=len(chunk_data),
    data=chunk_data,           # Store actual data
    checksum=real_checksum     # Real checksum from data
)
```

## Thread Safety Strategy

### Lock Hierarchy (to prevent deadlocks)
1. **Network-level locks** (StorageVirtualNetwork.lock)
2. **Node-level locks** (StorageVirtualNode locks)
3. **Component-level locks** (ReplicationManager.lock, HeartbeatMonitor locks)

### Lock Types
- **RLock (Reentrant Lock):** For operations that may call themselves recursively
  - `StorageVirtualNode.transfer_lock`
  - `StorageVirtualNetwork.lock`
  - `ReplicationManager.lock`

- **Lock (Standard Lock):** For simple critical sections
  - `StorageVirtualNode.storage_lock`
  - `StorageVirtualNode.bandwidth_lock`

### Best Practices
- Always use `with lock:` context manager
- Keep critical sections small
- Never call external code while holding lock
- Acquire locks in consistent order

## Configuration System

### Config Hierarchy
```
Config
├── SystemConfig
├── ReplicationConfig
├── MonitoringConfig
├── ChunkingConfig
├── NetworkConfig
├── StorageConfig
├── LoadBalancingConfig
├── LoggingConfig
├── PerformanceConfig
├── TestingConfig
├── MetricsConfig
└── SecurityConfig
```

### Configuration Loading
```python
# Load from YAML
config = Config.load("config.yaml")

# Access nested config
replication_factor = config.replication.default_factor
heartbeat_interval = config.monitoring.heartbeat_interval
```

## Logging System

### Log Levels
- **DEBUG:** Detailed diagnostic information
- **INFO:** General informational messages
- **WARNING:** Warning messages (e.g., under-replication)
- **ERROR:** Error messages (e.g., transfer failures)
- **CRITICAL:** Critical errors (e.g., data loss)

### Log Outputs
1. **Console:** Colored output for development
2. **File:** Rotating file handler (10MB max, 5 backups)

### Log Format
```
2024-01-15 10:30:45 [INFO    ] Node node-1: Transfer completed (1024 bytes)
```

## Performance Characteristics

### Adaptive Chunking
- File < 10MB: 512KB chunks
- File 10-100MB: 2MB chunks
- File > 100MB: 10MB chunks

**Rationale:** Balance between:
- Small chunks: More parallelism, higher overhead
- Large chunks: Less overhead, less parallelism

### Network Simulation
```python
transfer_time = chunk_size_bits / available_bandwidth
if latency_simulation_enabled:
    transfer_time += base_latency_ms / 1000.0
time.sleep(transfer_time)
```

### Load Balancing
**Least Loaded Strategy:**
```python
candidates.sort(
    key=lambda n: n.total_storage - n.used_storage,
    reverse=True
)
selected = candidates[:count]
```

## Scalability Considerations

### Horizontal Scaling
- Add more StorageVirtualNode instances
- Network coordinator handles all nodes
- No theoretical limit on node count

### Bottlenecks
1. **Coordinator:** Single point of coordination
   - Mitigation: Lightweight operations, async processing
2. **Network Bandwidth:** Limited by simulation
   - Mitigation: Configurable bandwidth per node
3. **Storage Capacity:** Limited by node capacity
   - Mitigation: Add more nodes

### Future Improvements
- **Distributed Coordinator:** Multiple coordinators with consensus
- **Hierarchical Architecture:** Regional coordinators
- **Caching:** Frequently accessed chunks cached in memory

## Fault Tolerance

### Failure Scenarios Handled
1. ✅ **Single Node Failure:** Data remains available (2/3 replicas)
2. ✅ **Multiple Node Failures:** Data available if ≥1 replica survives
3. ✅ **Network Partition:** Detected via heartbeat timeout
4. ✅ **Slow Node:** Load balancer avoids overloaded nodes

### Failure Scenarios NOT Handled
1. ❌ **Coordinator Failure:** Single point of failure
2. ❌ **Simultaneous Failure of All Replicas:** Data loss
3. ❌ **Byzantine Failures:** Malicious nodes not detected
4. ❌ **Network Partition with Split Brain:** No consensus protocol

## Testing Strategy

### Unit Tests
- `test_storage_node.py`: Node operations, checksums, bandwidth
- `test_replication.py`: Replica placement, failure handling
- `test_heartbeat.py`: Failure detection, recovery

### Integration Tests
- `test_integration.py`: End-to-end scenarios, multi-node operations

### Test Coverage Target
- Minimum: 60%
- Target: 80%
- Critical paths: 100%

## Comparison with Production Systems

### HDFS (Hadoop Distributed File System)
| Feature | HDFS | CloudSim |
|---------|------|----------|
| Architecture | Master-Slave | Master-Slave ✅ |
| Replication | 3x default | 3x default ✅ |
| Block Size | 128MB | 512KB-10MB ⚠️ |
| Heartbeat | 3s interval | 3s interval ✅ |
| Failure Detection | 30s timeout | 30s timeout ✅ |
| Rack Awareness | Yes | No ❌ |
| Checksums | CRC32 | SHA-256 ✅ |

### Amazon S3
| Feature | S3 | CloudSim |
|---------|-----|----------|
| CAP | AP (Eventual) | CP (Strong) ⚠️ |
| Durability | 11 nines | 3x replication ⚠️ |
| Availability | 99.99% | Depends on cluster ⚠️ |
| Replication | Cross-region | Single cluster ❌ |
| Versioning | Yes | No ❌ |
| Encryption | Yes | No ❌ |

## Security Considerations

### Current Implementation
- ✅ Data integrity via SHA-256 checksums
- ✅ Checksum verification on read/write
- ❌ No encryption at rest
- ❌ No encryption in transit
- ❌ No authentication
- ❌ No authorization

### Future Security Enhancements
- Encryption at rest (AES-256)
- TLS for network communication
- Authentication (API keys, OAuth)
- Authorization (ACLs, RBAC)
- Audit logging

---

**Document Version:** 1.0  
**Last Updated:** 2024-01-15  
**Status:** Production-Ready Baseline

