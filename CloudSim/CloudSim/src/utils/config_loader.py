"""
Configuration Loader
Loads and validates configuration from YAML file
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class SystemConfig:
    """System-wide configuration"""
    name: str = "CloudSim"
    version: str = "2.0.0"
    environment: str = "production"


@dataclass
class ReplicationConfig:
    """Replication settings"""
    default_factor: int = 3
    min_factor: int = 2
    max_factor: int = 5
    placement_strategy: str = "diverse"


@dataclass
class MonitoringConfig:
    """Monitoring and heartbeat settings"""
    heartbeat_interval: int = 3
    failure_timeout: int = 30
    recovery_check_interval: int = 5
    enable_auto_recovery: bool = True


@dataclass
class ChunkingConfig:
    """Chunk sizing configuration"""
    small_file_threshold: int = 10 * 1024 * 1024  # 10 MB
    medium_file_threshold: int = 100 * 1024 * 1024  # 100 MB
    small_chunk_size: int = 512 * 1024  # 512 KB
    medium_chunk_size: int = 2 * 1024 * 1024  # 2 MB
    large_chunk_size: int = 10 * 1024 * 1024  # 10 MB


@dataclass
class NetworkConfig:
    """Network settings"""
    max_bandwidth_per_node: int = 10000  # Mbps
    connection_timeout: int = 30
    retry_attempts: int = 3
    retry_delay: int = 2
    enable_bandwidth_throttling: bool = True


@dataclass
class StorageConfig:
    """Storage settings"""
    enable_compression: bool = False
    enable_encryption: bool = False
    checksum_algorithm: str = "sha256"
    verify_on_read: bool = True
    verify_on_write: bool = True


@dataclass
class LoadBalancingConfig:
    """Load balancing configuration"""
    strategy: str = "least_loaded"
    rebalance_threshold: float = 0.2
    enable_auto_rebalance: bool = False


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "detailed"
    log_to_file: bool = True
    log_to_console: bool = True
    log_file_path: str = "logs/cloudsim.log"
    max_log_file_size: int = 10 * 1024 * 1024  # 10 MB
    backup_count: int = 5


@dataclass
class PerformanceConfig:
    """Performance settings"""
    enable_caching: bool = False
    cache_size_mb: int = 100
    max_concurrent_transfers: int = 10
    chunk_transfer_timeout: int = 300
    enable_parallel_transfers: bool = True


@dataclass
class TestingConfig:
    """Testing and debugging settings"""
    enable_failure_injection: bool = False
    failure_probability: float = 0.01
    enable_latency_simulation: bool = True
    base_latency_ms: int = 10


@dataclass
class MetricsConfig:
    """Metrics and monitoring configuration"""
    enable_prometheus: bool = False
    prometheus_port: int = 9090
    metrics_interval: int = 60
    enable_detailed_metrics: bool = True


@dataclass
class SecurityConfig:
    """Security settings (future features)"""
    enable_authentication: bool = False
    enable_authorization: bool = False
    enable_encryption: bool = False
    enable_audit_log: bool = False


@dataclass
class Config:
    """Main configuration class"""
    system: SystemConfig = field(default_factory=SystemConfig)
    replication: ReplicationConfig = field(default_factory=ReplicationConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    load_balancing: LoadBalancingConfig = field(default_factory=LoadBalancingConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    testing: TestingConfig = field(default_factory=TestingConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    @classmethod
    def load(cls, config_path: str = "config.yaml") -> "Config":
        """Load configuration from YAML file"""
        try:
            if not os.path.exists(config_path):
                logger.warning(f"Config file {config_path} not found, using defaults")
                return cls()

            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)

            if not data:
                logger.warning("Empty config file, using defaults")
                return cls()

            # Create config objects from YAML data
            config = cls()
            
            if 'system' in data:
                config.system = SystemConfig(**data['system'])
            if 'replication' in data:
                config.replication = ReplicationConfig(**data['replication'])
            if 'monitoring' in data:
                config.monitoring = MonitoringConfig(**data['monitoring'])
            if 'chunking' in data:
                config.chunking = ChunkingConfig(**data['chunking'])
            if 'network' in data:
                config.network = NetworkConfig(**data['network'])
            if 'storage' in data:
                config.storage = StorageConfig(**data['storage'])
            if 'load_balancing' in data:
                config.load_balancing = LoadBalancingConfig(**data['load_balancing'])
            if 'logging' in data:
                config.logging = LoggingConfig(**data['logging'])
            if 'performance' in data:
                config.performance = PerformanceConfig(**data['performance'])
            if 'testing' in data:
                config.testing = TestingConfig(**data['testing'])
            if 'metrics' in data:
                config.metrics = MetricsConfig(**data['metrics'])
            if 'security' in data:
                config.security = SecurityConfig(**data['security'])

            logger.info(f"Configuration loaded from {config_path}")
            return config

        except Exception as e:
            logger.error(f"Error loading config: {e}, using defaults")
            return cls()

    def validate(self) -> bool:
        """Validate configuration values"""
        errors = []

        # Validate replication
        if self.replication.default_factor < 1:
            errors.append("Replication factor must be >= 1")
        if self.replication.min_factor > self.replication.default_factor:
            errors.append("Min replication factor cannot exceed default")

        # Validate monitoring
        if self.monitoring.heartbeat_interval <= 0:
            errors.append("Heartbeat interval must be > 0")
        if self.monitoring.failure_timeout <= self.monitoring.heartbeat_interval:
            errors.append("Failure timeout must be > heartbeat interval")

        # Validate chunking
        if self.chunking.small_chunk_size <= 0:
            errors.append("Chunk sizes must be > 0")

        # Validate network
        if self.network.retry_attempts < 0:
            errors.append("Retry attempts must be >= 0")

        if errors:
            for error in errors:
                logger.error(f"Config validation error: {error}")
            return False

        logger.info("Configuration validated successfully")
        return True


# Global config instance
_config: Optional[Config] = None


def get_config(config_path: str = "config.yaml") -> Config:
    """Get global configuration instance"""
    global _config
    if _config is None:
        _config = Config.load(config_path)
        _config.validate()
    return _config


def reload_config(config_path: str = "config.yaml") -> Config:
    """Reload configuration from file"""
    global _config
    _config = Config.load(config_path)
    _config.validate()
    return _config

