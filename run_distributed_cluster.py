#!/usr/bin/env python3
"""Helper script to launch the distributed CloudSim stack.

This orchestrates the real coordinator and storage nodes as separate OS
processes so you can interact with the system through the TCP interface
(e.g., via ``cloudsim_client.py``). It mirrors the manual steps described
in the documentation:

    1. Start the coordinator on its own port.
    2. Launch one storage node per terminal/port.
    3. Drive uploads/downloads via ``cloudsim_client.py``.

You can still start each script in its own terminal manually. This helper
simply automates the sequence and optionally keeps output attached to the
current console for convenience.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).parent
PYTHON = sys.executable or "python"
DEFAULT_STORAGE_GB = [100, 150, 200, 250, 300]

try:
    CREATE_NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
except AttributeError:  # Non-Windows platforms
    CREATE_NEW_CONSOLE = 0


def _script_path(name: str) -> str:
    return str(ROOT / name)


@dataclass
class ProcessHandle:
    name: str
    process: subprocess.Popen
    output_thread: Optional[threading.Thread] = None

    def terminate(self, timeout: float = 5.0) -> None:
        if self.process.poll() is not None:
            return

        try:
            if os.name == "nt":
                self.process.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                self.process.terminate()
        except Exception:
            pass

        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()


def stream_output(proc: subprocess.Popen, name: str) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"[{name}] {line.rstrip()}" )
    proc.stdout.close()


def launch(cmd: List[str], name: str, detach: bool) -> ProcessHandle:
    kwargs = {
        "cwd": str(ROOT),
        "text": True,
        "bufsize": 1,
    }

    if detach and CREATE_NEW_CONSOLE:
        kwargs["stdout"] = None
        kwargs["stderr"] = None
        kwargs["creationflags"] = CREATE_NEW_CONSOLE
    else:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.STDOUT

    proc = subprocess.Popen(cmd, **kwargs)

    output_thread = None
    if kwargs["stdout"] is not None:
        output_thread = threading.Thread(target=stream_output, args=(proc, name), daemon=True)
        output_thread.start()

    return ProcessHandle(name=name, process=proc, output_thread=output_thread)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch CloudSim distributed coordinator and nodes")
    parser.add_argument("--coordinator-host", default="localhost", help="Host for the coordinator (default: localhost)")
    parser.add_argument("--coordinator-port", type=int, default=5000, help="Port for coordinator (default: 5000)")
    parser.add_argument("--nodes", type=int, default=3, help="Number of storage nodes to launch (default: 3)")
    parser.add_argument(
        "--base-node-port",
        type=int,
        default=6001,
        help="First node port; each node increments by 1 (default: 6001)",
    )
    parser.add_argument(
        "--storage-gb",
        default="",
        help="Comma-separated list of per-node storage GB (cycles if shorter). Default sequence: 100,150,200,250,300",
    )
    parser.add_argument(
        "--detach-terminals",
        action="store_true",
        help="On Windows, open each coordinator/node in its own console window.",
    )
    parser.add_argument(
        "--status-on-start",
        action="store_true",
        help="Call cloudsim_client.py status once the cluster is ready.",
    )
    return parser.parse_args()


def build_storage_plan(args: argparse.Namespace) -> List[int]:
    if args.storage_gb:
        values = [int(value.strip()) for value in args.storage_gb.split(",") if value.strip()]
        if not values:
            raise ValueError("--storage-gb must contain at least one integer value")
        return values
    return DEFAULT_STORAGE_GB


def start_coordinator(args: argparse.Namespace, detach: bool) -> ProcessHandle:
    cmd = [PYTHON, _script_path("start_coordinator.py"), "--host", args.coordinator_host, "--port", str(args.coordinator_port)]
    print(f"[runner] Starting coordinator on {args.coordinator_host}:{args.coordinator_port}...")
    return launch(cmd, name="coordinator", detach=detach)


def start_nodes(args: argparse.Namespace, detach: bool) -> List[ProcessHandle]:
    handles: List[ProcessHandle] = []
    storages = build_storage_plan(args)
    base_port = args.base_node_port

    for index in range(args.nodes):
        node_id = f"node-{index + 1}"
        port = base_port + index
        storage_gb = storages[index % len(storages)]
        cmd = [
            PYTHON,
            _script_path("start_node.py"),
            node_id,
            "--host",
            args.coordinator_host,
            "--port",
            str(port),
            "--storage",
            str(storage_gb),
            "--coordinator-host",
            args.coordinator_host,
            "--coordinator-port",
            str(args.coordinator_port),
        ]
        print(f"[runner] Starting {node_id} on port {port} ({storage_gb} GB)...")
        handles.append(launch(cmd, name=node_id, detach=detach))
        time.sleep(0.5)

    return handles


def wait_for_cluster(handles: List[ProcessHandle]) -> bool:
    time.sleep(2)
    for handle in handles:
        if handle.process.poll() is not None:
            print(f"[runner] Process '{handle.name}' exited early (code {handle.process.returncode}). See logs above.")
            return False
    print("[runner] All processes appear healthy.")
    return True


def show_status(args: argparse.Namespace) -> None:
    cmd = [
        PYTHON,
        _script_path("cloudsim_client.py"),
        "status",
        "--coordinator",
        f"{args.coordinator_host}:{args.coordinator_port}",
    ]
    print("[runner] Fetching cluster status via cloudsim_client.py ...")
    subprocess.run(cmd, cwd=str(ROOT), check=False)


def shutdown(handles: List[ProcessHandle]) -> None:
    print("\n[runner] Shutting down processes...")
    for handle in handles:
        print(f"[runner] Stopping {handle.name}...")
        handle.terminate()
    print("[runner] Shutdown complete.")


def main() -> None:
    args = parse_args()
    detach = args.detach_terminals and os.name == "nt"

    process_handles: List[ProcessHandle] = []

    try:
        coordinator = start_coordinator(args, detach=detach)
        process_handles.append(coordinator)
        time.sleep(1.5)

        node_handles = start_nodes(args, detach=detach)
        process_handles.extend(node_handles)

        if not wait_for_cluster(process_handles):
            raise SystemExit(1)

        if args.status_on_start:
            show_status(args)

        print("\n[runner] Coordinator and nodes are running. Use cloudsim_client.py to upload/download files.")
        print("[runner] Press Ctrl+C to stop the cluster.")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[runner] Caught Ctrl+C. Initiating shutdown...")
    finally:
        shutdown(process_handles)


if __name__ == "__main__":
    main()
