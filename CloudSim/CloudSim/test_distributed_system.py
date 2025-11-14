#!/usr/bin/env python3
"""
Test script for distributed CloudSim system.
Tests the complete distributed system with coordinator and nodes.
"""

import subprocess
import time
import sys
import os
import signal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.network import NetworkClient, create_message, MessageType


class DistributedSystemTester:
    """Test the distributed CloudSim system."""
    
    def __init__(self):
        self.processes = []
        self.coordinator_host = 'localhost'
        self.coordinator_port = 5000
        
    def start_coordinator(self):
        """Start the coordinator process."""
        print("[1/4] Starting coordinator...")
        
        cmd = [
            sys.executable,
            'start_coordinator.py',
            '--host', self.coordinator_host,
            '--port', str(self.coordinator_port)
        ]
        
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        self.processes.append(('coordinator', proc))
        time.sleep(2)  # Give coordinator time to start
        
        # Check if coordinator is running
        if proc.poll() is not None:
            print("  ✗ Coordinator failed to start")
            return False
        
        print("  ✓ Coordinator started on port 5000")
        return True
    
    def start_nodes(self, num_nodes=3):
        """Start storage nodes."""
        print(f"\n[2/4] Starting {num_nodes} storage nodes...")
        
        base_port = 6001
        storage_sizes = [100, 150, 200, 250, 300]  # GB
        
        for i in range(num_nodes):
            node_id = f"node-{i+1}"
            port = base_port + i
            storage = storage_sizes[i % len(storage_sizes)]
            
            cmd = [
                sys.executable,
                'start_node.py',
                node_id,
                '--host', 'localhost',
                '--port', str(port),
                '--storage', str(storage),
                '--coordinator-host', self.coordinator_host,
                '--coordinator-port', str(self.coordinator_port)
            ]
            
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            self.processes.append((node_id, proc))
            time.sleep(1)  # Stagger node starts
            
            # Check if node is running
            if proc.poll() is not None:
                print(f"  ✗ {node_id} failed to start")
                return False
            
            print(f"  ✓ {node_id} started on port {port} ({storage}GB)")
        
        # Give nodes time to register
        time.sleep(2)
        return True
    
    def test_system_status(self):
        """Test getting system status."""
        print("\n[3/4] Testing system status...")
        
        try:
            message = create_message(MessageType.GET_STATUS, {})
            
            with NetworkClient() as client:
                if not client.connect(self.coordinator_host, self.coordinator_port):
                    print("  ✗ Could not connect to coordinator")
                    return False
                
                response = client.send_and_receive(message)
                if not response:
                    print("  ✗ No response from coordinator")
                    return False
                
                response_msg, _ = response
                
                if response_msg.msg_type == MessageType.STATUS_RESPONSE:
                    data = response_msg.data
                    print(f"  ✓ System status retrieved:")
                    print(f"    - Total Nodes: {data['total_nodes']}")
                    print(f"    - Healthy Nodes: {data['healthy_nodes']}")
                    print(f"    - Total Storage: {data['total_storage'] / (1024**3):.2f} GB")
                    return data['healthy_nodes'] > 0
                else:
                    print(f"  ✗ Unexpected response: {response_msg.msg_type.value}")
                    return False
        
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return False
    
    def test_file_upload(self):
        """Test file upload."""
        print("\n[4/4] Testing file upload...")
        
        # Create test file
        test_file = 'test_upload.bin'
        test_data = b'A' * (5 * 1024 * 1024)  # 5 MB
        
        try:
            with open(test_file, 'wb') as f:
                f.write(test_data)
            
            print(f"  ✓ Created test file: {test_file} (5 MB)")
            
            # Use client to upload
            cmd = [
                sys.executable,
                'cloudsim_client.py',
                'upload',
                test_file,
                '--coordinator', f'{self.coordinator_host}:{self.coordinator_port}',
                '--replication', '3'
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print("  ✓ File uploaded successfully")
                
                # Show some output
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'File ID:' in line or 'uploaded' in line.lower():
                        print(f"    {line.strip()}")
                
                return True
            else:
                print(f"  ✗ Upload failed")
                print(f"    Error: {result.stderr}")
                return False
        
        except Exception as e:
            print(f"  ✗ Error: {e}")
            return False
        
        finally:
            # Cleanup
            if os.path.exists(test_file):
                os.remove(test_file)
    
    def cleanup(self):
        """Stop all processes."""
        print("\n[CLEANUP] Stopping all processes...")
        
        for name, proc in self.processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
                print(f"  ✓ Stopped {name}")
            except subprocess.TimeoutExpired:
                proc.kill()
                print(f"  ✓ Killed {name}")
            except Exception as e:
                print(f"  ✗ Error stopping {name}: {e}")
    
    def run_tests(self):
        """Run all tests."""
        print("="*70)
        print("  CloudSim Distributed System Test")
        print("="*70)
        print()
        
        try:
            # Start coordinator
            if not self.start_coordinator():
                print("\n✗ TEST FAILED: Coordinator did not start")
                return False
            
            # Start nodes
            if not self.start_nodes(num_nodes=3):
                print("\n✗ TEST FAILED: Nodes did not start")
                return False
            
            # Test status
            if not self.test_system_status():
                print("\n✗ TEST FAILED: System status check failed")
                return False
            
            # Test upload
            if not self.test_file_upload():
                print("\n✗ TEST FAILED: File upload failed")
                return False
            
            print("\n" + "="*70)
            print("  ✓ ALL TESTS PASSED")
            print("="*70)
            return True
        
        except KeyboardInterrupt:
            print("\n\nTest interrupted by user")
            return False
        
        except Exception as e:
            print(f"\n✗ TEST FAILED: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            self.cleanup()


def main():
    tester = DistributedSystemTester()
    success = tester.run_tests()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

