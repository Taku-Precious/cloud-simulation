#!/usr/bin/env python3
"""End-to-end demo for the virtualization layer on top of CloudSim."""

import os
import pprint
import sys
import time
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent))

from src.core.storage_network import StorageVirtualNetwork
from src.virtualization import (
    GlobalLoadPlacementController,
    OperatingSystemProfile,
    NodeProvisionRequest,
    TcpIpSimulator,
    VirtualInfrastructureManager,
)
from src.utils.logger import setup_logging, get_logger


def _print_banner(title: str) -> None:
    print("\n" + "=" * 90)
    print(f"  {title}")
    print("=" * 90 + "\n")


def main() -> None:
    setup_logging(log_to_file=False)
    logger = get_logger(__name__)

    _print_banner("CloudSim Virtualization Demo")

    network = StorageVirtualNetwork()
    vim = VirtualInfrastructureManager(network, ip_cidr="10.10.0.0/24")
    glpc = GlobalLoadPlacementController(network)
    tcp_simulator = TcpIpSimulator(bandwidth_kbps=64, latency_ms=20)

    # Define OS profiles for heterogeneous fleet
    os_profiles = {
        "ubuntu-lts": OperatingSystemProfile(
            name="Ubuntu Server",
            version="24.04 LTS",
            kernel="linux-6.8",
            packages=("openssh", "docker", "prometheus-node-exporter"),
            hardening_level="cis-level-1",
        ),
        "rocky": OperatingSystemProfile(
            name="Rocky Linux",
            version="9.4",
            kernel="linux-5.14",
            packages=("podman", "firewalld", "cloud-init"),
            hardening_level="stig",
        ),
        "windows": OperatingSystemProfile(
            name="Windows Server",
            version="2025",
            kernel="nt-kernel-10.0",
            packages=("HyperV", "IIS", "Defender"),
            hardening_level="secure-baseline",
        ),
    }

    # Provision additional distributed storage nodes with explicit OS assignments
    node_requests = [
        NodeProvisionRequest("vs-node-1", 32, 128, 400, 2000, os_profiles["ubuntu-lts"]),
        NodeProvisionRequest("vs-node-2", 24, 96, 350, 1500, os_profiles["rocky"]),
        NodeProvisionRequest("vs-node-3", 32, 192, 500, 2500, os_profiles["ubuntu-lts"]),
        NodeProvisionRequest("vs-node-4", 16, 64, 300, 1000, os_profiles["windows"]),
        NodeProvisionRequest("vs-node-5", 20, 80, 320, 1200, os_profiles["rocky"]),
        NodeProvisionRequest("vs-node-6", 28, 128, 450, 1800, os_profiles["ubuntu-lts"]),
        NodeProvisionRequest("vs-node-7", 12, 48, 250, 800, os_profiles["rocky"]),
        NodeProvisionRequest("vs-node-8", 40, 256, 600, 3000, os_profiles["windows"]),
    ]

    logger.info("Provisioning %d distributed nodes...", len(node_requests))
    provisioned_nodes = vim.provision_nodes(node_requests)

    # Create a simple mesh network among the new nodes
    for i, node_a in enumerate(provisioned_nodes):
        for node_b in provisioned_nodes[i + 1 :]:
            bw = min(node_a.bandwidth, node_b.bandwidth) // 1_000_000  # back to Mbps for API
            network.connect_nodes(node_a.node_id, node_b.node_id, bw)

    network.start()
    time.sleep(1.5)  # allow heartbeat monitor to gather first samples

    _print_banner("Creating Distributed Virtual Storage Volumes")
    analytics_vol = vim.create_virtual_storage("analytics-tier", 80, replication_factor=3)
    archive_vol = vim.create_virtual_storage("archive-tier", 120, replication_factor=2)
    hot_path_vol = vim.create_virtual_storage("hot-path", 60, replication_factor=3)
    edge_cache_vol = vim.create_virtual_storage("edge-cache", 40, replication_factor=2)
    ai_training_vol = vim.create_virtual_storage("ai-training", 150, replication_factor=3)

    _print_banner("Launching Virtual Machines with Distributed IPs")
    def _deploy_vm(name: str, profile: OperatingSystemProfile, volumes, preferred=None, min_hosts=2):
        required_nodes = sorted({node for vid in volumes for node in vim.volumes[vid].backing_nodes})
        decision = glpc.select_nodes_for_vm(
            required_nodes=required_nodes,
            preferred_nodes=preferred,
            min_count=max(min_hosts, len(required_nodes) or 1),
        )
        vm = vim.deploy_virtual_machine(
            name=name,
            os_profile=profile,
            volume_ids=volumes,
            preferred_nodes=decision.nodes,
        )
        logger.info("GLPC placed %s on %s (%s)", name, decision.nodes, decision.reason)
        return vm

    vm1 = _deploy_vm(
        name="analytics-vm-1",
        profile=os_profiles["ubuntu-lts"],
        volumes=[analytics_vol.volume_id, hot_path_vol.volume_id],
    )

    vm2 = _deploy_vm(
        name="archiver-vm-1",
        profile=os_profiles["rocky"],
        volumes=[archive_vol.volume_id],
    )

    vm3 = _deploy_vm(
        name="windows-ingest",
        profile=os_profiles["windows"],
        volumes=[hot_path_vol.volume_id],
        preferred=["vs-node-4", "vs-node-8"],
    )

    vm4 = _deploy_vm(
        name="edge-cache",
        profile=os_profiles["ubuntu-lts"],
        volumes=[edge_cache_vol.volume_id],
        preferred=["vs-node-6", "vs-node-7"],
    )

    vm5 = _deploy_vm(
        name="ai-trainer",
        profile=os_profiles["rocky"],
        volumes=[ai_training_vol.volume_id, analytics_vol.volume_id],
        preferred=["vs-node-3", "vs-node-8"],
        min_hosts=3,
    )

    vm_inventory = [vm1, vm2, vm3, vm4, vm5]

    print("Assigned VM IP addresses:")
    for vm in vm_inventory:
        print(
            f"  - {vm.name:<15} | VM ID: {vm.vm_id} | IP: {vm.ip_address} | Nodes: {', '.join(vm.nodes)}"
        )

    _print_banner("Simulating TCP/IP File Transfer @64kbps")
    sample_file = os.urandom(256 * 1024)  # 256 KB sample payload
    file_id = network.initiate_file_transfer_with_replication(
        file_name="glpc-sample.bin",
        file_data=sample_file,
        replication_factor=3,
    )

    if file_id:
        def _drive_transfer():
            while True:
                chunks, complete = network.process_file_transfer(file_id=file_id, chunks_per_step=5)
                if complete:
                    break
                if chunks == 0:
                    time.sleep(0.2)

        outcome = tcp_simulator.simulate_transfer(len(sample_file), transfer_callable=_drive_transfer)
        print(
            "  • File ID:", file_id,
            "\n  • Theoretical duration: %.2fs" % outcome.simulated_duration,
            "\n  • Measured duration:   %.2fs" % outcome.measured_duration,
        )
    else:
        print("Failed to initiate sample transfer")

    _print_banner("Investigating Distributed Storage Cloud State")
    report = vim.generate_investigation_report()
    pprint.pprint(report)

    _print_banner("Shutting Down")
    network.stop()
    print("Demo complete.")


if __name__ == "__main__":
    main()
